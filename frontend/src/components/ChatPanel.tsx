import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Message } from '../types.ts'

interface Props {
  summary?: string
  messages: Message[]
  streamingContent: string
  onSend: (text: string) => void
  isStreaming: boolean
  className?: string
}

export default function ChatPanel({ summary, messages, streamingContent, onSend, isStreaming, className }: Props) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, isStreaming])

  function handleSend() {
    const text = input.trim()
    if (!text || isStreaming) return
    onSend(text)
    setInput('')
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <main className={`panel-middle${className ? ` ${className}` : ''}`}>
      {summary && (
        <div className="summary-section">
          <h2>Summary</h2>
          <p>{summary}</p>
        </div>
      )}

      <div className="chat-section">
        <div className="chat-messages">
          {messages.length === 0 && !streamingContent ? (
            <div className="chat-empty">
              <span className="chat-empty-icon">💬</span>
              <p>Ask a question about your sources</p>
            </div>
          ) : (
            <>
              {messages.map((msg, i) => (
                <div key={i} className={`chat-bubble ${msg.role}`}>
                  {msg.role === 'assistant' ? (
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  ) : (
                    msg.content
                  )}
                </div>
              ))}

              {/* Processing / streaming bubble */}
              {isStreaming && !streamingContent && (
                <div className="chat-bubble assistant">
                  <span className="typing-dots">
                    <span /><span /><span />
                  </span>
                </div>
              )}
              {streamingContent && (
                <div className="chat-bubble assistant streaming">
                  <ReactMarkdown>{streamingContent}</ReactMarkdown>
                  <span className="cursor-blink" />
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input-bar">
          <textarea
            rows={1}
            placeholder="Ask anything about your sources…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
          />
          <button
            className="btn-send"
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
          >
            {isStreaming ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </main>
  )
}

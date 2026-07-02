import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ChatPanel from '../components/ChatPanel.tsx'
import SourcesPanel from '../components/SourcesPanel.tsx'
import ToolsPanel from '../components/ToolsPanel.tsx'
import type { AddSourceData, Message, NotebookDetail } from '../types.ts'

export default function NotebookPage() {
  const { id } = useParams<{ id: string }>()

  const [notebook, setNotebook] = useState<NotebookDetail | null>(null)
  const [loadingNotebook, setLoadingNotebook] = useState(true)
  const [addingSource, setAddingSource] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [mobileTab, setMobileTab] = useState<'sources' | 'chat' | 'tools'>('chat')

  useEffect(() => {
    if (!id) return
    setLoadingNotebook(true)
    fetch(`/api/notebooks/${id}`, { credentials: 'include' })
      .then(r => r.json())
      .then(setNotebook)
      .catch(console.error)
      .finally(() => setLoadingNotebook(false))

    fetch(`/api/notebooks/${id}/chat`, { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.messages?.length) setMessages(data.messages) })
      .catch(() => {})
  }, [id])

  async function handleAddSource(data: AddSourceData, onProgress: (step: string, pct: number) => void) {
    if (!id) return
    setAddingSource(true)
    try {
      const form = new FormData()
      if (data.type === 'file' && data.files) {
        for (const f of data.files) form.append('files', f)
      }
      if (data.type === 'url' && data.urls) form.append('urls', data.urls)
      if (data.type === 'text' && data.text) form.append('text', data.text)
      form.append('anonymize', data.anonymize ? 'true' : 'false')

      const res = await fetch(`/api/notebooks/${id}/sources`, {
        method: 'POST',
        credentials: 'include',
        body: form,
      })

      if (!res.ok || !res.body) throw new Error('Server error')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let result: Record<string, unknown> | null = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() ?? ''
        for (const chunk of chunks) {
          const dataLine = chunk.split('\n').find(l => l.startsWith('data: '))
          if (!dataLine) continue
          let event: Record<string, unknown>
          try { event = JSON.parse(dataLine.slice(6)) } catch { continue }
          if (event.type === 'progress') {
            onProgress(event.step as string, event.progress as number)
          } else if (event.type === 'result') {
            result = event.data as Record<string, unknown>
          } else if (event.type === 'error') {
            throw new Error(event.message as string)
          }
        }
      }

      if (result) {
        setNotebook(prev => prev ? {
          ...prev,
          title: result!.title as string,
          sources: [...prev.sources, ...((result!.sources ?? []) as typeof prev.sources)],
          documentation: result!.documentation as string | null,
          summary: result!.summary as string | null,
        } : prev)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setAddingSource(false)
    }
  }

  async function handleSend(text: string) {
    if (!id || isStreaming) return

    const userMsg: Message = { role: 'user', content: text }
    const nextHistory = [...messages, userMsg]
    setMessages(nextHistory)
    setIsStreaming(true)
    setStreamingContent('')

    try {
      const res = await fetch(`/api/notebooks/${id}/chat`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: nextHistory, query: text }),
      })

      if (!res.ok || !res.body) {
        setMessages(prev => [...prev, { role: 'assistant', content: 'Error: could not reach the server.' }])
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const raw = decoder.decode(value, { stream: true })
        for (const line of raw.split('\n')) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue
          const payload = trimmed.slice(5).trim()
          if (payload === '[DONE]') break
          try {
            const parsed = JSON.parse(payload) as { content?: string; error?: string }
            if (parsed.error) {
              accumulated += `\n\n*Error: ${parsed.error}*`
            } else if (parsed.content) {
              accumulated += parsed.content
            }
            setStreamingContent(accumulated)
          } catch {
            // partial JSON — skip
          }
        }
      }

      const finalMessages = [...nextHistory, { role: 'assistant' as const, content: accumulated }]
      setMessages(finalMessages)

      fetch(`/api/notebooks/${id}/chat/history`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: finalMessages }),
      }).catch(() => {})
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error: network failure.' }])
      console.error(err)
    } finally {
      setStreamingContent('')
      setIsStreaming(false)
    }
  }

  if (loadingNotebook) {
    return (
      <div className="notebook-page">
        <header className="notebook-header">
          <Link to="/" className="btn-ghost" style={{ textDecoration: 'none' }}>← Back</Link>
          <span className="notebook-header-title">Loading…</span>
        </header>
        <div className="notebook-layout" />
        <nav className="mobile-tab-bar" />
      </div>
    )
  }

  const title = notebook?.title ?? 'Notebook'

  return (
    <div className="notebook-page">
      <header className="notebook-header">
        <Link to="/" className="btn-ghost" style={{ textDecoration: 'none' }}>← Back</Link>
        <span className="notebook-header-title">{title}</span>
        {addingSource && (
          <span style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 12 }}>
            Processing source…
          </span>
        )}
      </header>

      <div className="notebook-layout">
        <SourcesPanel
          className={mobileTab !== 'sources' ? 'mobile-hidden' : 'mobile-active'}
          sources={notebook?.sources ?? []}
          onAddSource={handleAddSource}
        />
        <ChatPanel
          className={mobileTab !== 'chat' ? 'mobile-hidden' : 'mobile-active'}
          summary={notebook?.summary ?? undefined}
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
          onSend={handleSend}
        />
        <ToolsPanel
          className={mobileTab !== 'tools' ? 'mobile-hidden' : 'mobile-active'}
          notebookId={id ?? ''}
        />
      </div>

      <nav className="mobile-tab-bar">
        <button
          className={`mobile-tab${mobileTab === 'sources' ? ' active' : ''}`}
          onClick={() => setMobileTab('sources')}
        >
          <span className="mobile-tab-icon">📁</span>
          <span>Sources</span>
        </button>
        <button
          className={`mobile-tab${mobileTab === 'chat' ? ' active' : ''}`}
          onClick={() => setMobileTab('chat')}
        >
          <span className="mobile-tab-icon">💬</span>
          <span>Chat</span>
        </button>
        <button
          className={`mobile-tab${mobileTab === 'tools' ? ' active' : ''}`}
          onClick={() => setMobileTab('tools')}
        >
          <span className="mobile-tab-icon">🔬</span>
          <span>Tools</span>
        </button>
      </nav>
    </div>
  )
}

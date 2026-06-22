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

  async function handleAddSource(data: AddSourceData) {
    if (!id) return
    setAddingSource(true)
    try {
      const form = new FormData()
      if (data.type === 'pdf' && data.files) {
        for (const f of data.files) form.append('files', f)
      }
      if (data.type === 'url' && data.urls) form.append('urls', data.urls)
      if (data.type === 'text' && data.text) form.append('text', data.text)

      const res = await fetch(`/api/notebooks/${id}/sources`, {
        method: 'POST',
        credentials: 'include',
        body: form,
      })
      const result = await res.json()

      setNotebook(prev => prev ? {
        ...prev,
        title: result.title,
        sources: [...prev.sources, ...(result.sources ?? [])],
        documentation: result.documentation,
        summary: result.summary,
      } : prev)
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
          sources={notebook?.sources ?? []}
          onAddSource={handleAddSource}
        />
        <ChatPanel
          summary={notebook?.summary ?? undefined}
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
          onSend={handleSend}
        />
        <ToolsPanel notebookId={id ?? ''} />
      </div>
    </div>
  )
}

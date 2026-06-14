import { useRef, useState } from 'react'
import type { AddSourceData } from '../types.ts'

interface Props {
  onClose: () => void
  onSubmit: (data: AddSourceData) => Promise<void>
}

type Tab = 'pdf' | 'url' | 'text'

export default function AddSourceModal({ onClose, onSubmit }: Props) {
  const [tab, setTab] = useState<Tab>('pdf')
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const canSubmit =
    tab === 'pdf' ? file !== null
    : tab === 'url' ? url.trim().length > 0
    : text.trim().length > 0

  async function handleSubmit() {
    if (!canSubmit || loading) return
    setLoading(true)
    try {
      if (tab === 'pdf' && file) {
        await onSubmit({ type: 'pdf', file })
      } else if (tab === 'url') {
        await onSubmit({ type: 'url', url: url.trim() })
      } else if (tab === 'text') {
        await onSubmit({ type: 'text', text: text.trim() })
      }
      onClose()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add source</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-tabs">
          <button
            className={`modal-tab ${tab === 'pdf' ? 'active' : ''}`}
            onClick={() => setTab('pdf')}
          >
            Upload PDF
          </button>
          <button
            className={`modal-tab ${tab === 'url' ? 'active' : ''}`}
            onClick={() => setTab('url')}
          >
            Paste URL
          </button>
          <button
            className={`modal-tab ${tab === 'text' ? 'active' : ''}`}
            onClick={() => setTab('text')}
          >
            Enter text
          </button>
        </div>

        <div className="modal-body">
          {tab === 'pdf' && (
            <label className="file-drop-zone">
              <input
                type="file"
                accept=".pdf"
                ref={fileInputRef}
                onChange={e => setFile(e.target.files?.[0] ?? null)}
              />
              <div className="file-drop-zone-icon">📄</div>
              {file
                ? <span style={{ color: 'var(--text)' }}>{file.name}</span>
                : <span>Click to choose a PDF</span>
              }
            </label>
          )}

          {tab === 'url' && (
            <input
              type="url"
              placeholder="https://pubmed.ncbi.nlm.nih.gov/…"
              value={url}
              onChange={e => setUrl(e.target.value)}
              autoFocus
            />
          )}

          {tab === 'text' && (
            <textarea
              rows={8}
              placeholder="Paste or type clinical notes, guidelines, or any text…"
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
              style={{ width: '100%', resize: 'vertical', fontFamily: 'inherit', fontSize: 14 }}
            />
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-ghost" onClick={onClose} disabled={loading}>Cancel</button>
          <button className="btn-primary" onClick={handleSubmit} disabled={!canSubmit || loading}>
            {loading ? 'Processing…' : 'Add source'}
          </button>
        </div>
      </div>
    </div>
  )
}

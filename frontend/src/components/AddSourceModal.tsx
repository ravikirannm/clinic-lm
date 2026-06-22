import { useRef, useState } from 'react'
import type { AddSourceData } from '../types.ts'

interface Props {
  onClose: () => void
  onSubmit: (data: AddSourceData) => Promise<void>
}

type Tab = 'pdf' | 'url' | 'text'

export default function AddSourceModal({ onClose, onSubmit }: Props) {
  const [tab, setTab] = useState<Tab>('pdf')
  const [urls, setUrls] = useState('')
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [loading, setLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const canSubmit =
    tab === 'pdf' ? files.length > 0
    : tab === 'url' ? urls.trim().length > 0
    : text.trim().length > 0

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(e.target.files ?? []))
  }

  async function handleSubmit() {
    if (!canSubmit || loading) return
    setLoading(true)
    try {
      if (tab === 'pdf') {
        await onSubmit({ type: 'pdf', files })
      } else if (tab === 'url') {
        await onSubmit({ type: 'url', urls: urls.trim() })
      } else {
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
                multiple
                ref={fileInputRef}
                onChange={handleFileChange}
              />
              <div className="file-drop-zone-icon">📄</div>
              {files.length === 0 && <span>Click to choose one or more PDFs</span>}
              {files.length === 1 && <span style={{ color: 'var(--text)' }}>{files[0].name}</span>}
              {files.length > 1 && (
                <span style={{ color: 'var(--text)' }}>{files.length} files selected</span>
              )}
            </label>
          )}

          {tab === 'url' && (
            <textarea
              rows={5}
              placeholder={"https://pubmed.ncbi.nlm.nih.gov/…\nhttps://example.com/guideline.html"}
              value={urls}
              onChange={e => setUrls(e.target.value)}
              autoFocus
              style={{ width: '100%', resize: 'vertical', fontFamily: 'inherit', fontSize: 14 }}
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

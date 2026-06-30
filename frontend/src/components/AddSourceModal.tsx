import { useRef, useState } from 'react'
import type { AddSourceData } from '../types.ts'

interface Props {
  onClose: () => void
  onSubmit: (data: AddSourceData) => Promise<void>
}

type Tab = 'file' | 'url' | 'text'

const ACCEPTED = '.pdf,.docx,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.tif,.webp'
const MAX_MB = 20

function fileIcon(file: File): string {
  if (file.type.startsWith('image/')) return '🖼️'
  if (file.name.toLowerCase().endsWith('.docx')) return '📝'
  return '📄'
}

export default function AddSourceModal({ onClose, onSubmit }: Props) {
  const [tab, setTab] = useState<Tab>('file')
  const [urls, setUrls] = useState('')
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState('')
  const [anonymize, setAnonymize] = useState(false)
  const [loading, setLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const canSubmit =
    tab === 'file' ? files.length > 0 && !fileError
    : tab === 'url' ? urls.trim().length > 0
    : text.trim().length > 0

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? [])
    const oversized = selected.filter(f => f.size > MAX_MB * 1024 * 1024)
    if (oversized.length > 0) {
      setFileError(`${oversized.map(f => f.name).join(', ')} exceed${oversized.length === 1 ? 's' : ''} the ${MAX_MB} MB limit`)
      setFiles([])
    } else {
      setFileError('')
      setFiles(selected)
    }
  }

  async function handleSubmit() {
    if (!canSubmit || loading) return
    setLoading(true)
    try {
      if (tab === 'file') {
        await onSubmit({ type: 'file', files, anonymize })
      } else if (tab === 'url') {
        await onSubmit({ type: 'url', urls: urls.trim(), anonymize })
      } else {
        await onSubmit({ type: 'text', text: text.trim(), anonymize })
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
            className={`modal-tab ${tab === 'file' ? 'active' : ''}`}
            onClick={() => setTab('file')}
          >
            Upload file
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
          {tab === 'file' && (
            <>
              <label className="file-drop-zone">
                <input
                  type="file"
                  accept={ACCEPTED}
                  multiple
                  ref={fileInputRef}
                  onChange={handleFileChange}
                />
                <div className="file-drop-zone-icon">
                  {files.length === 1 ? fileIcon(files[0]) : '📂'}
                </div>
                {files.length === 0 && (
                  <span>Click to choose one or more files</span>
                )}
                {files.length === 1 && (
                  <span style={{ color: 'var(--text)' }}>{files[0].name}</span>
                )}
                {files.length > 1 && (
                  <span style={{ color: 'var(--text)' }}>{files.length} files selected</span>
                )}
              </label>
              <p style={{ margin: '6px 0 0', fontSize: 11, color: 'var(--text-muted)' }}>
                Accepted: PDF, DOCX, JPG, PNG, GIF, BMP, TIFF, WebP · Max {MAX_MB} MB per file
              </p>
              {fileError && (
                <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--error, #d32f2f)' }}>
                  {fileError}
                </p>
              )}
            </>
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

        <div style={{ padding: '8px 16px', background: 'var(--surface-2)', borderTop: '1px solid var(--border)', fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          Select "De-identify PII/PHI" to automatically redact names, dates, addresses, and other personal identifiers from the source before saving. This may add processing time.
        </div>

        <div className="modal-footer" >
          <div style={{display: 'flex', alignItems: 'center'}}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 0, fontSize: 13, color: 'var(--text-muted)', justifyContent:'start',  whiteSpace: 'nowrap', cursor: 'pointer', width: 'fit-content' }}>
                <span>
                  <input style={{marginRight:0}}
                  type="checkbox"
                  checked={anonymize}
                  onChange={e => setAnonymize(e.target.checked)}
                />
                </span>
                <span>De-identify PII/PHI</span>
              </label>
          </div>
          
          <button className="btn-ghost" onClick={onClose} disabled={loading}>Cancel</button>
          <button className="btn-primary" onClick={handleSubmit} disabled={!canSubmit || loading}>
            {loading ? 'Processing…' : 'Add source'}
          </button>
        </div>
      </div>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCurrentUser } from '../context/UserContext'
import type { RagDoc } from '../types'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function RagDocsPage() {
  const { user, logout } = useCurrentUser()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [docs, setDocs] = useState<RagDoc[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [confirmDeleteName, setConfirmDeleteName] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')

  function loadDocs() {
    setLoading(true)
    fetch('/api/rag-docs', { credentials: 'include' })
      .then(r => r.json())
      .then(setDocs)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadDocs() }, [])

  async function handleUpload(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return
    setUploading(true)
    setError('')
    setStatus('')
    try {
      const form = new FormData()
      for (const f of Array.from(fileList)) form.append('files', f)
      const res = await fetch('/api/rag-docs', {
        method: 'POST',
        credentials: 'include',
        body: form,
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Upload failed'); return }
      if (data.errors?.length) {
        setError(data.errors.map((e: { file: string; error: string }) => `${e.file}: ${e.error}`).join('; '))
      }
      if (data.saved?.length) {
        setStatus(`Uploaded ${data.saved.length} file(s). Click "Rebuild index" to embed them.`)
      }
      loadDocs()
    } catch {
      setError('Network error')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function confirmDelete() {
    if (!confirmDeleteName) return
    setDeleting(true)
    try {
      const res = await fetch(`/api/rag-docs/${encodeURIComponent(confirmDeleteName)}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (res.ok) {
        setDocs(prev => prev.filter(d => d.name !== confirmDeleteName))
        setConfirmDeleteName(null)
        setStatus('Deleted. Click "Rebuild index" to remove it from the knowledge base.')
      }
    } catch {
      console.error('Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  async function handleReindex() {
    setReindexing(true)
    setError('')
    setStatus('Rebuilding index — this re-embeds every document and may take a while…')
    try {
      const res = await fetch('/api/rag-docs/reindex', {
        method: 'POST',
        credentials: 'include',
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Reindex failed'); setStatus(''); return }
      setStatus(`Indexed ${data.documents_indexed} document(s) into ${data.chunks} chunk(s).`)
      if (data.errors?.length) {
        setError(data.errors.map((e: { file: string; error: string }) => `${e.file}: ${e.error}`).join('; '))
      }
    } catch {
      setError('Network error')
      setStatus('')
    } finally {
      setReindexing(false)
      setConfirmReset(false)
    }
  }

  return (
    <div className="notebooks-page">
      <div className="notebooks-header">
        <div>
          <h1>Clinic LM</h1>
          <p>AI-powered clinical notebooks</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{user?.name}</span>
          <button className="btn-ghost" onClick={logout} style={{ fontSize: 13 }}>Sign out</button>
        </div>
      </div>

      <div className="page-tabs">
        <button className="page-tab" onClick={() => navigate('/')}>Notebooks</button>
        <button className="page-tab" onClick={() => navigate('/users')}>Users</button>
        <button className="page-tab page-tab--active">RAG Docs</button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)', maxWidth: 520 }}>
          Documents here feed the medical knowledge base used by RAG retrieval. Upload or delete
          files, then rebuild the index so changes take effect.
        </p>
        <button
          className="btn-primary"
          style={{ background: 'var(--danger, #e53e3e)', whiteSpace: 'nowrap' }}
          onClick={() => setConfirmReset(true)}
          disabled={reindexing}
        >
          {reindexing ? 'Rebuilding…' : 'Rebuild index'}
        </button>
      </div>

      {error && <p style={{ color: 'var(--danger, #e53e3e)', fontSize: 13, marginBottom: 8 }}>{error}</p>}
      {status && !error && <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 8 }}>{status}</p>}

      <label className="file-drop-zone" style={{ marginBottom: 16 }}>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.tif,.webp"
          onChange={e => handleUpload(e.target.files)}
          disabled={uploading}
        />
        <div className="file-drop-zone-icon">📄</div>
        {uploading ? 'Uploading…' : 'Click to upload PDF, DOCX, or image documents'}
      </label>

      <div className="users-table-wrap">
        {loading ? (
          <p style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 13 }}>Loading…</p>
        ) : (
          <>
            <table className="users-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Size</th>
                  <th>Modified</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {docs.map(d => (
                  <tr key={d.name}>
                    <td>{d.name}</td>
                    <td style={{ color: 'var(--text-muted)' }}>{formatSize(d.size)}</td>
                    <td style={{ color: 'var(--text-muted)' }}>{new Date(d.modified * 1000).toLocaleString()}</td>
                    <td>
                      <button
                        className="btn-ghost"
                        style={{ padding: '4px 10px', fontSize: 12, color: 'var(--danger, #e53e3e)' }}
                        onClick={() => setConfirmDeleteName(d.name)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {docs.length === 0 && (
              <p style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 13 }}>
                No documents yet. Upload some to build the knowledge base.
              </p>
            )}
          </>
        )}
      </div>

      {confirmDeleteName && (
        <div className="modal-backdrop" onClick={() => !deleting && setConfirmDeleteName(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 380 }}>
            <div className="modal-header">
              <h3>Delete document</h3>
              <button className="btn-close" onClick={() => setConfirmDeleteName(null)} disabled={deleting}>×</button>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0, fontSize: 14 }}>
                Delete <strong>{confirmDeleteName}</strong>? This removes the file from disk.
                Rebuild the index afterward to remove it from search results.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn-ghost" onClick={() => setConfirmDeleteName(null)} disabled={deleting}>Cancel</button>
              <button
                className="btn-primary"
                onClick={confirmDelete}
                disabled={deleting}
                style={{ background: 'var(--danger, #e53e3e)' }}
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmReset && (
        <div className="modal-backdrop" onClick={() => !reindexing && setConfirmReset(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modal-header">
              <h3>Rebuild index</h3>
              <button className="btn-close" onClick={() => setConfirmReset(false)} disabled={reindexing}>×</button>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0, fontSize: 14 }}>
                This clears the current medical knowledge base and re-embeds every document
                currently in the list ({docs.length}). This may take a while and cannot be undone.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn-ghost" onClick={() => setConfirmReset(false)} disabled={reindexing}>Cancel</button>
              <button
                className="btn-primary"
                onClick={handleReindex}
                disabled={reindexing}
                style={{ background: 'var(--danger, #e53e3e)' }}
              >
                {reindexing ? 'Rebuilding…' : 'Clear & rebuild'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

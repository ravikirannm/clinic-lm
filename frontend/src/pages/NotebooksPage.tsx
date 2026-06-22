import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { Notebook } from '../types.ts'

export default function NotebooksPage() {
  const navigate = useNavigate()
  const [notebooks, setNotebooks] = useState<Notebook[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<Notebook | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    fetch('/api/notebooks', { credentials: 'include' })
      .then(r => r.json())
      .then(setNotebooks)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  async function handleNew() {
    setCreating(true)
    try {
      const res = await fetch('/api/notebooks', {
        method: 'POST',
        credentials: 'include',
      })
      const data = await res.json()
      navigate(`/notebook/${data.notebook_id}`)
    } catch (err) {
      console.error(err)
      setCreating(false)
    }
  }

  async function handleDelete() {
    if (!confirmDelete) return
    setDeleting(true)
    try {
      await fetch(`/api/notebooks/${confirmDelete.id}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      setNotebooks(prev => prev.filter(nb => nb.id !== confirmDelete.id))
      setConfirmDelete(null)
    } catch (err) {
      console.error(err)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="notebooks-page">
      <div className="notebooks-header">
        <div>
          <h1>Clinic LM</h1>
          <p>AI-powered clinical notebooks</p>
        </div>
        <button className="btn-primary" onClick={handleNew} disabled={creating}>
          {creating ? 'Creating…' : '+ New notebook'}
        </button>
      </div>

      <div className="notebooks-list">
        {loading ? (
          <p style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 13 }}>
            Loading…
          </p>
        ) : notebooks.length === 0 ? (
          <p style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 13 }}>
            No notebooks yet. Create one to get started.
          </p>
        ) : (
          notebooks.map(nb => (
            <Link key={nb.id} to={`/notebook/${nb.id}`} className="notebook-list-item">
              <span className="notebook-list-item-icon">📓</span>
              <span className="notebook-list-item-title">{nb.title}</span>
              <div className="notebook-list-item-meta">
                <span>{nb.sourceCount} sources</span>
                <span>{nb.updatedAt}</span>
              </div>
              <button
                onClick={e => { e.preventDefault(); e.stopPropagation(); setConfirmDelete(nb) }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: 'var(--text-muted)', lineHeight: 1, padding: '4px 2px', flexShrink: 0 }}
                title="Delete notebook"
              >
                ×
              </button>
            </Link>
          ))
        )}
      </div>

      {confirmDelete && (
        <div className="modal-backdrop" onClick={() => !deleting && setConfirmDelete(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 380 }}>
            <div className="modal-header">
              <h3>Delete notebook</h3>
              <button className="btn-close" onClick={() => setConfirmDelete(null)} disabled={deleting}>×</button>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0, fontSize: 14 }}>
                Delete <strong>{confirmDelete.title}</strong>? This will permanently remove all sources and generated content.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn-ghost" onClick={() => setConfirmDelete(null)} disabled={deleting}>Cancel</button>
              <button
                className="btn-primary"
                onClick={handleDelete}
                disabled={deleting}
                style={{ background: 'var(--danger, #e53e3e)' }}
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

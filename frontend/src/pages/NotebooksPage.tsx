import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { Notebook } from '../types.ts'

export default function NotebooksPage() {
  const navigate = useNavigate()
  const [notebooks, setNotebooks] = useState<Notebook[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

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
              <span className="notebook-list-item-arrow">›</span>
            </Link>
          ))
        )}
      </div>
    </div>
  )
}

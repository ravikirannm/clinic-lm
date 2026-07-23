import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCurrentUser } from '../context/UserContext'
import { ROLES } from '../types'
import type { UserRecord } from '../types'

export default function UsersPage() {
  const { user, logout } = useCurrentUser()
  const navigate = useNavigate()

  const [users, setUsers] = useState<UserRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editRole, setEditRole] = useState<number>(1)
  const [saving, setSaving] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/users', { credentials: 'include' })
      .then(r => r.json())
      .then(setUsers)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  function startEdit(u: UserRecord) {
    setEditingId(u.user_id)
    setEditName(u.name)
    setEditRole(u.role_id)
    setError('')
  }

  function cancelEdit() {
    setEditingId(null)
    setError('')
  }

  async function saveEdit(userId: string) {
    setSaving(true)
    setError('')
    try {
      const res = await fetch(`/api/users/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ name: editName.trim(), role_id: editRole }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Update failed'); return }
      setUsers(prev => prev.map(u =>
        u.user_id === userId ? { ...u, name: editName.trim(), role_id: editRole as UserRecord['role_id'] } : u
      ))
      setEditingId(null)
    } catch {
      setError('Network error')
    } finally {
      setSaving(false)
    }
  }

  async function confirmDelete() {
    if (!confirmDeleteId) return
    setDeleting(true)
    try {
      const res = await fetch(`/api/users/${confirmDeleteId}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (res.ok) {
        setUsers(prev => prev.filter(u => u.user_id !== confirmDeleteId))
        setConfirmDeleteId(null)
      }
    } catch {
      console.error('Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  const userToDelete = users.find(u => u.user_id === confirmDeleteId)

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
        <button className="page-tab page-tab--active">Users</button>
        <button className="page-tab" onClick={() => navigate('/rag-docs')}>RAG Docs</button>
      </div>

      <div className="users-table-wrap">
        {loading ? (
          <p style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 13 }}>Loading…</p>
        ) : (
          <>
            {error && <p style={{ color: 'var(--danger, #e53e3e)', fontSize: 13, marginBottom: 8 }}>{error}</p>}
            <table className="users-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Verified</th>
                  <th>Joined</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.user_id}>
                    {editingId === u.user_id ? (
                      <>
                        <td>
                          <input
                            value={editName}
                            onChange={e => setEditName(e.target.value)}
                            style={{ padding: '4px 8px', fontSize: 13 }}
                          />
                        </td>
                        <td style={{ color: 'var(--text-muted)' }}>{u.email}</td>
                        <td>
                          <select
                            value={editRole}
                            onChange={e => setEditRole(Number(e.target.value))}
                            className="users-role-select"
                          >
                            {Object.values(ROLES).map(r => (
                              <option key={r.id} value={r.id}>{r.label}</option>
                            ))}
                          </select>
                        </td>
                        <td>{u.is_verified ? 'Yes' : 'No'}</td>
                        <td>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button
                              className="btn-primary"
                              style={{ padding: '4px 10px', fontSize: 12 }}
                              onClick={() => saveEdit(u.user_id)}
                              disabled={saving}
                            >
                              {saving ? 'Saving…' : 'Save'}
                            </button>
                            <button
                              className="btn-ghost"
                              style={{ padding: '4px 10px', fontSize: 12 }}
                              onClick={cancelEdit}
                              disabled={saving}
                            >
                              Cancel
                            </button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td>{u.name}</td>
                        <td style={{ color: 'var(--text-muted)' }}>{u.email}</td>
                        <td>
                          <span className={`role-badge role-badge--${ROLES[u.role_id]?.name ?? 'free'}`}>
                            {ROLES[u.role_id]?.label ?? 'Unknown'}
                          </span>
                        </td>
                        <td>{u.is_verified ? 'Yes' : 'No'}</td>
                        <td>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button
                              className="btn-ghost"
                              style={{ padding: '4px 10px', fontSize: 12 }}
                              onClick={() => startEdit(u)}
                            >
                              Edit
                            </button>
                            {u.user_id !== user?.user_id && (
                              <button
                                className="btn-ghost"
                                style={{ padding: '4px 10px', fontSize: 12, color: 'var(--danger, #e53e3e)' }}
                                onClick={() => setConfirmDeleteId(u.user_id)}
                              >
                                Delete
                              </button>
                            )}
                          </div>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {users.length === 0 && (
              <p style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 13 }}>No users found.</p>
            )}
          </>
        )}
      </div>

      {confirmDeleteId && (
        <div className="modal-backdrop" onClick={() => !deleting && setConfirmDeleteId(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 380 }}>
            <div className="modal-header">
              <h3>Delete user</h3>
              <button className="btn-close" onClick={() => setConfirmDeleteId(null)} disabled={deleting}>×</button>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0, fontSize: 14 }}>
                Delete <strong>{userToDelete?.name}</strong> ({userToDelete?.email})?
                This will permanently remove their account and all associated data.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn-ghost" onClick={() => setConfirmDeleteId(null)} disabled={deleting}>Cancel</button>
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
    </div>
  )
}

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.scss'
import { UserProvider, useCurrentUser } from './context/UserContext'
import AuthPage from './pages/AuthPage'
import NotebooksPage from './pages/NotebooksPage'
import NotebookPage from './pages/NotebookPage'
import UsersPage from './pages/UsersPage'

function AppRoutes() {
  const { user, loading } = useCurrentUser()

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--text-muted)', fontSize: 14 }}>
        Loading…
      </div>
    )
  }

  if (!user) return <AuthPage />

  return (
    <Routes>
      <Route path="/" element={<NotebooksPage />} />
      <Route path="/notebook/:id" element={<NotebookPage />} />
      {user.role_id === 3 && (
        <Route path="/users" element={<UsersPage />} />
      )}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <UserProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </UserProvider>
  )
}

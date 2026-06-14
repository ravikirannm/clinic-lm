import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.scss'
import { UserProvider } from './context/UserContext.tsx'
import NotebooksPage from './pages/NotebooksPage.tsx'
import NotebookPage from './pages/NotebookPage.tsx'

export default function App() {
  return (
    <UserProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<NotebooksPage />} />
          <Route path="/notebook/:id" element={<NotebookPage />} />
        </Routes>
      </BrowserRouter>
    </UserProvider>
  )
}

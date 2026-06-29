import { useState, type FormEvent } from 'react'
import { useCurrentUser } from '../context/UserContext'

type Step = 'email' | 'register' | 'otp'

export default function AuthPage() {
  const { refresh } = useCurrentUser()

  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [otp, setOtp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleEmailSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/request-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: email.trim() }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Something went wrong'); return }
      if (data.status === 'registration_required') {
        setStep('register')
      } else {
        setStep('otp')
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  async function handleRegisterSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (!name.trim()) { setError('Please enter your name.'); return }
    setLoading(true)
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: email.trim(), name: name.trim() }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Registration failed'); return }
      setStep('otp')
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  async function handleOtpSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: email.trim(), otp: otp.trim() }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Verification failed'); return }
      await refresh()
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-logo">Clinic LM</h1>
        <p className="auth-tagline">AI-powered clinical notebooks</p>

        {step === 'email' && (
          <form onSubmit={handleEmailSubmit} className="auth-form">
            <label className="auth-label">Email address</label>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
            />
            {error && <p className="auth-error">{error}</p>}
            <button className="btn-primary auth-btn" type="submit" disabled={loading}>
              {loading ? 'Checking…' : 'Continue'}
            </button>
          </form>
        )}

        {step === 'register' && (
          <form onSubmit={handleRegisterSubmit} className="auth-form">
            <p className="auth-hint">No account found for <strong>{email}</strong>. Enter your name to register.</p>
            <label className="auth-label">Full name</label>
            <input
              type="text"
              placeholder="Dr. Jane Smith"
              value={name}
              onChange={e => setName(e.target.value)}
              required
              autoFocus
            />
            {error && <p className="auth-error">{error}</p>}
            <button className="btn-primary auth-btn" type="submit" disabled={loading}>
              {loading ? 'Sending code…' : 'Create account & send code'}
            </button>
            <button
              type="button"
              className="btn-ghost auth-back"
              onClick={() => { setStep('email'); setError('') }}
            >
              Back
            </button>
          </form>
        )}

        {step === 'otp' && (
          <form onSubmit={handleOtpSubmit} className="auth-form">
            <p className="auth-hint">
              A 6-digit code was sent to <strong>{email}</strong>. Enter it below.
            </p>
            <label className="auth-label">Verification code</label>
            <input
              type="text"
              inputMode="numeric"
              placeholder="123456"
              maxLength={6}
              value={otp}
              onChange={e => setOtp(e.target.value.replace(/\D/g, ''))}
              required
              autoFocus
            />
            {error && <p className="auth-error">{error}</p>}
            <button className="btn-primary auth-btn" type="submit" disabled={loading}>
              {loading ? 'Verifying…' : 'Sign in'}
            </button>
            <button
              type="button"
              className="btn-ghost auth-back"
              onClick={() => { setStep('email'); setOtp(''); setError('') }}
            >
              Use a different email
            </button>
          </form>
        )}
      </div>
    </div>
  )
}

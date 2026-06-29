import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { DraftResult } from '../types.ts'

interface Props {
  drafts: DraftResult
  initialType?: string
  onClose: () => void
}

const TYPE_ORDER = ['referral_letter', 'discharge_summary', 'case_writeup']
const TYPE_LABELS: Record<string, string> = {
  referral_letter:   'Referral Letter',
  discharge_summary: 'Discharge Summary',
  case_writeup:      'Case Write-up',
}

function useIsMobile() {
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 768px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const fn = (e: MediaQueryListEvent) => setMobile(e.matches)
    mq.addEventListener('change', fn)
    return () => mq.removeEventListener('change', fn)
  }, [])
  return mobile
}

export default function DocumentDrafterModal({ drafts, initialType, onClose }: Props) {
  const available = TYPE_ORDER.filter(t => drafts[t])
  const defaultType = initialType && drafts[initialType] ? initialType : (available[0] ?? 'referral_letter')
  const [activeType, setActiveType] = useState(defaultType)
  const [copied, setCopied] = useState(false)
  const isMobile = useIsMobile()

  const draft = drafts[activeType]

  function handleCopy() {
    if (!draft) return
    navigator.clipboard.writeText(draft.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  function formatDate(iso: string) {
    try {
      return new Date(iso).toLocaleString('en-GB', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 820, maxWidth: '96vw', maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}
      >
        {/* Header */}
        <div className="modal-header" style={{ paddingBottom: 14 }}>
          <h3>Document Drafter</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div style={{ overflowY: 'auto', padding: '0 24px 24px', flex: 1 }}>

          {/* Document type selector + copy icon row */}
          <div style={controlRow}>
            {isMobile ? (
              <div style={{ display: 'flex', gap: 6, flex: 1, flexWrap: 'wrap' }}>
                {available.map(t => (
                  <button
                    key={t}
                    onClick={() => { setActiveType(t); setCopied(false) }}
                    style={{
                      padding: '7px 14px',
                      borderRadius: 20,
                      border: activeType === t ? '1.5px solid var(--accent)' : '1px solid var(--border)',
                      background: activeType === t ? 'var(--accent)' : 'var(--surface-2)',
                      color: activeType === t ? '#fff' : 'var(--text)',
                      fontSize: 13,
                      fontWeight: activeType === t ? 600 : 400,
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {TYPE_LABELS[t] ?? t}
                  </button>
                ))}
              </div>
            ) : (
              <select
                value={activeType}
                onChange={e => { setActiveType(e.target.value); setCopied(false) }}
                style={selectStyle}
              >
                {available.map(t => (
                  <option key={t} value={t}>{TYPE_LABELS[t] ?? t}</option>
                ))}
              </select>
            )}

            {draft && (
              <button onClick={handleCopy} style={copyBtn} title="Copy to clipboard">
                {copied ? (
                  <>
                    <CopyIcon checked />
                    <span style={{ fontSize: 12, color: '#22c55e', fontWeight: 600 }}>Copied</span>
                  </>
                ) : (
                  <>
                    <CopyIcon />
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Copy</span>
                  </>
                )}
              </button>
            )}
          </div>

          {draft ? (
            <>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
                Generated {formatDate(draft.generated_at)}
              </div>
              <div style={docBody} className="draft-doc-body">
                <ReactMarkdown>{draft.content}</ReactMarkdown>
              </div>
            </>
          ) : (
            <div style={emptyBox}>No draft available for this document type.</div>
          )}
        </div>
      </div>
    </div>
  )
}

function CopyIcon({ checked = false }: { checked?: boolean }) {
  return checked ? (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ) : (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const controlRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  marginTop: 8,
  marginBottom: 8,
}

const selectStyle: React.CSSProperties = {
  flex: 1,
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  color: 'var(--text)',
  fontSize: 14,
  fontWeight: 500,
  padding: '8px 12px',
  cursor: 'pointer',
}

const copyBtn: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  padding: '6px 12px',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  flexShrink: 0,
}

const docBody: React.CSSProperties = {
  background: '#ffffff',
  color: '#1a1a1a',
  fontFamily: '"Georgia", "Times New Roman", serif',
  fontSize: 14,
  lineHeight: 1.8,
  padding: '32px 40px',
  borderRadius: 8,
  border: '1px solid #d1d5db',
  boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
}

const emptyBox: React.CSSProperties = {
  marginTop: 20,
  padding: '24px',
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  fontSize: 13,
  color: 'var(--text-muted)',
  textAlign: 'center',
}

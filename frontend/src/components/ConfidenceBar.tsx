interface Props {
  confidence: number
}

export default function ConfidenceBar({ confidence }: Props) {
  const pct     = Math.round(Math.max(0, Math.min(1, confidence)) * 100)
  const label   = pct >= 75 ? 'High' : pct >= 50 ? 'Moderate' : 'Low'
  const txtColor = pct >= 75 ? '#22c55e' : pct >= 50 ? '#f59e0b' : '#ef4444'

  return (
    <div style={{ margin: '14px 0 2px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
        <span style={{
          fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
          letterSpacing: '0.06em', color: 'var(--text-muted)',
        }}>
          Analysis Confidence — {label}
        </span>
        <span style={{ fontSize: 13, fontWeight: 700, color: txtColor }}>{pct}%</span>
      </div>

      {/* Gradient bar: red → yellow → green, right portion masked */}
      <div style={{
        height: 8, borderRadius: 6, overflow: 'hidden', position: 'relative',
        background: 'linear-gradient(to right, #ef4444 0%, #f59e0b 45%, #22c55e 100%)',
      }}>
        <div style={{
          position: 'absolute',
          left: `${pct}%`, right: 0, top: 0, bottom: 0,
          background: 'var(--surface-2)',
          opacity: 0.88,
        }} />
      </div>
    </div>
  )
}

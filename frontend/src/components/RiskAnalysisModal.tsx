import { useState } from 'react'
import type { RiskAnalysisResult, ScoreResult, RiskCriterion } from '../types.ts'

interface Props {
  result: RiskAnalysisResult
  onClose: () => void
}

const SCORE_META: {
  key: keyof RiskAnalysisResult['scores']
  label: string
  subtitle: string
  unit: string
}[] = [
  { key: 'wells_dvt',    label: 'Wells DVT',      subtitle: 'DVT Probability',    unit: '/9' },
  { key: 'cha2ds2_vasc', label: 'CHA₂DS₂-VASc',  subtitle: 'Stroke Risk Score',  unit: '/9' },
  { key: 'qsofa',        label: 'qSOFA',           subtitle: 'Sepsis Risk',        unit: '/3' },
  { key: 'meld',         label: 'MELD',            subtitle: 'Liver Disease',      unit: '/40' },
]

export default function RiskAnalysisModal({ result, onClose }: Props) {
  const { scores } = result
  const [activeKey, setActiveKey] = useState<keyof typeof scores>('wells_dvt')
  const active = scores[activeKey]

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 820, maxWidth: '95vw', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
      >
        <div className="modal-header" style={{ paddingBottom: 14 }}>
          <h3>Risk Analysis</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div style={{ overflowY: 'auto', padding: '0 24px 24px', flex: 1 }}>

          {/* Score summary cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginTop: 16 }}>
            {SCORE_META.map(({ key, label, subtitle, unit }) => {
              const s = scores[key]
              const isActive = key === activeKey
              return (
                <button
                  key={key}
                  onClick={() => setActiveKey(key)}
                  style={scoreCard(isActive, s.risk_level)}
                >
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>
                    {label}
                  </div>
                  <div style={{ fontSize: 28, fontWeight: 700, lineHeight: 1, color: riskColor(s.risk_level) }}>
                    {s.score ?? '—'}
                    <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-muted)' }}>{unit}</span>
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <span style={riskBadge(s.risk_level)}>{s.risk_level}</span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{subtitle}</div>
                </button>
              )
            })}
          </div>

          {/* Detail panel for selected score */}
          <div style={{ marginTop: 20 }}>
            <ScoreDetail score={active} label={SCORE_META.find(m => m.key === activeKey)!.label} />
          </div>
        </div>
      </div>
    </div>
  )
}

function ScoreDetail({ score, label }: { score: ScoreResult; label: string }) {
  const extra = [
    score.probability && `DVT probability: ${score.probability}`,
    score.annual_stroke_risk && `Annual stroke risk: ${score.annual_stroke_risk}`,
    score['3_month_mortality'] && `3-month mortality: ${score['3_month_mortality']}`,
    score.meld_na != null && `MELD-Na: ${score.meld_na}`,
    score.interpretation,
    score.recommendation,
  ].filter(Boolean)

  return (
    <div>
      {/* Key stats */}
      {extra.length > 0 && (
        <div style={infoBox}>
          {extra.map((e, i) => (
            <div key={i} style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.6 }}>{e as string}</div>
          ))}
        </div>
      )}

      {/* Criteria table */}
      <div style={{ marginTop: 14 }}>
        <div style={sectionLabel}>{label} — Criteria breakdown</div>
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
          {score.criteria.map((c, i) => (
            <CriterionRow key={i} criterion={c} last={i === score.criteria.length - 1} />
          ))}
        </div>
      </div>

      {/* Missing parameters */}
      {score.missing_parameters.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={sectionLabel}>Missing / Unknown Parameters</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {score.missing_parameters.map(m => (
              <span key={m} style={missingTag}>{m}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function CriterionRow({ criterion: c, last }: { criterion: RiskCriterion; last: boolean }) {
  const [open, setOpen] = useState(false)
  const awarded = c.points_awarded != null && c.points_awarded !== 0
  const isNumeric = c.points_possible == null  // MELD labs

  return (
    <div
      style={{
        borderBottom: last ? 'none' : '1px solid var(--border)',
        background: awarded ? 'var(--accent)0a' : 'transparent',
      }}
    >
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px', cursor: c.evidence ? 'pointer' : 'default' }}
        onClick={() => c.evidence && setOpen(o => !o)}
      >
        {!isNumeric && (
          <span style={{
            width: 20, height: 20, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 700, flexShrink: 0,
            background: awarded ? riskColor('High') + '22' : 'var(--surface-2)',
            color: awarded ? riskColor('High') : 'var(--text-muted)',
            border: `1px solid ${awarded ? riskColor('High') + '44' : 'var(--border)'}`,
          }}>
            {awarded ? `+${c.points_awarded}` : '·'}
          </span>
        )}
        <span style={{ flex: 1, fontSize: 13, color: 'var(--text)' }}>{c.criterion}</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', flexShrink: 0 }}>{c.status}</span>
        {c.evidence && (
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{open ? '▲' : '▼'}</span>
        )}
      </div>
      {open && c.evidence && (
        <div style={{ padding: '0 14px 10px 44px', fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>
          "{c.evidence}"
        </div>
      )}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

function riskColor(level: string): string {
  const l = level.toLowerCase()
  if (l.includes('high') || l.includes('critical') || l.includes('very')) return '#ef4444'
  if (l.includes('severe')) return '#f97316'
  if (l.includes('moderate') || l.includes('low-mod')) return '#f59e0b'
  if (l.includes('low')) return '#22c55e'
  return 'var(--text-muted)'
}

function riskBadge(level: string): React.CSSProperties {
  const color = riskColor(level)
  return {
    background: color + '1a',
    color,
    borderRadius: 4,
    padding: '2px 7px',
    fontSize: 11,
    fontWeight: 700,
  }
}

function scoreCard(active: boolean, riskLevel: string): React.CSSProperties {
  return {
    background: active ? 'var(--surface-2)' : 'transparent',
    border: `1px solid ${active ? riskColor(riskLevel) + '55' : 'var(--border)'}`,
    borderRadius: 'var(--radius)',
    padding: '14px 16px',
    cursor: 'pointer',
    textAlign: 'left',
    transition: 'border-color 0.15s',
  }
}

const infoBox: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '10px 14px',
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
}

const sectionLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 8,
}

const missingTag: React.CSSProperties = {
  background: '#f59e0b1a',
  color: '#f59e0b',
  borderRadius: 4,
  padding: '2px 8px',
  fontSize: 11,
  fontWeight: 500,
}

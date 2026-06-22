import { useState } from 'react'
import ConfidenceBar from './ConfidenceBar.tsx'
import type { GuidelinesConformanceResult, GuidelineFinding } from '../types.ts'

interface Props {
  result: GuidelinesConformanceResult
  onClose: () => void
}

type Tab = 'deviations' | 'conforming' | 'not_assessed'

export default function GuidelinesConformanceModal({ result, onClose }: Props) {
  const [tab, setTab] = useState<Tab>('deviations')

  const { deviations, conforming, not_assessed, overall_summary, guidelines_fetched, confidence } = result

  const majorCount = deviations.filter(d => d.severity === 'major').length
  const minorCount = deviations.filter(d => d.severity === 'minor').length

  const activeFindings =
    tab === 'deviations' ? deviations :
    tab === 'conforming' ? conforming :
    not_assessed

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 860, maxWidth: '96vw', maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}
      >
        <div className="modal-header" style={{ paddingBottom: 14 }}>
          <h3>Guidelines Conformance</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div style={{ overflowY: 'auto', padding: '0 24px 24px', flex: 1 }}>
          {confidence != null && <ConfidenceBar confidence={confidence} />}

          {/* Summary bar */}
          <div style={summaryBar}>
            <StatChip label="Sources retrieved" value={guidelines_fetched} color="var(--text-muted)" />
            <StatChip label="Deviations" value={deviations.length} color="#ef4444" />
            <StatChip label="Major" value={majorCount} color="#ef4444" />
            <StatChip label="Minor" value={minorCount} color="#f59e0b" />
            <StatChip label="Conforming" value={conforming.length} color="#22c55e" />
          </div>

          {/* Source breakdown */}
          {result.sources && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
              {[
                { label: 'PubMed',        count: result.sources.pubmed },
                { label: 'NCBI Bookshelf',count: result.sources.bookshelf },
                { label: 'MedlinePlus',   count: result.sources.medlineplus },
                { label: 'NLM Catalog',   count: result.sources.nlm_catalog },
              ].map(s => s.count > 0 && (
                <span key={s.label} style={sourcePill}>
                  {s.label} <strong>{s.count}</strong>
                </span>
              ))}
            </div>
          )}

          {/* Overall summary */}
          {overall_summary && (
            <div style={summaryBox}>
              <div style={sectionLabel}>Overall Assessment</div>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text)', lineHeight: 1.6 }}>
                {overall_summary}
              </p>
            </div>
          )}

          {/* Tabs */}
          <div style={tabBar}>
            <TabBtn active={tab === 'deviations'} onClick={() => setTab('deviations')}
              label={`Deviations (${deviations.length})`} accent="#ef4444" />
            <TabBtn active={tab === 'conforming'} onClick={() => setTab('conforming')}
              label={`Conforming (${conforming.length})`} accent="#22c55e" />
            <TabBtn active={tab === 'not_assessed'} onClick={() => setTab('not_assessed')}
              label={`Not Assessed (${not_assessed.length})`} accent="var(--text-muted)" />
          </div>

          {/* Finding cards */}
          {activeFindings.length === 0 ? (
            <div style={emptyBox}>No findings in this category.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
              {activeFindings.map((f, i) => <FindingCard key={i} finding={f} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function FindingCard({ finding: f }: { finding: GuidelineFinding }) {
  const [expanded, setExpanded] = useState(false)
  const isDeviation = f.status === 'deviation' || f.status === 'partial'

  return (
    <div style={cardStyle(f.status)}>
      {/* Header row */}
      <div
        style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }}
        onClick={() => setExpanded(v => !v)}
      >
        <StatusBadge status={f.status} />
        {isDeviation && <SeverityBadge severity={f.severity} />}
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{f.area}</div>
          {f.guideline_title && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              {f.pmid
                ? <a href={`https://pubmed.ncbi.nlm.nih.gov/${f.pmid}/`} target="_blank" rel="noreferrer"
                    style={{ color: 'var(--accent)', textDecoration: 'none' }}>
                    PMID {f.pmid} ↗
                  </a>
                : null}
              {f.pmid ? ' — ' : ''}{f.guideline_title}
            </div>
          )}
        </div>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <DetailRow label="Guideline recommendation" value={f.guideline_recommendation} />
          <DetailRow label="Current practice" value={f.current_practice} />
          {isDeviation && f.action && (
            <DetailRow label="Recommended action" value={f.action} highlight />
          )}
        </div>
      )}
    </div>
  )
}

function DetailRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{
      background: highlight ? '#f59e0b0d' : 'var(--surface)',
      border: `1px solid ${highlight ? '#f59e0b33' : 'var(--border)'}`,
      borderRadius: 6,
      padding: '8px 12px',
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.5 }}>{value}</div>
    </div>
  )
}

function StatChip({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '10px 16px', flex: 1 }}>
      <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{label}</div>
    </div>
  )
}

function TabBtn({ active, onClick, label, accent }: { active: boolean; onClick: () => void; label: string; accent: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'none',
        border: 'none',
        borderBottom: active ? `2px solid ${accent}` : '2px solid transparent',
        padding: '8px 14px',
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        color: active ? accent : 'var(--text-muted)',
        cursor: 'pointer',
        transition: 'color 0.15s',
      }}
    >
      {label}
    </button>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string }> = {
    deviation:    { label: 'Deviation',    color: '#ef4444' },
    partial:      { label: 'Partial',      color: '#f59e0b' },
    conforming:   { label: 'Conforming',   color: '#22c55e' },
    not_assessed: { label: 'N/A',          color: '#94a3b8' },
  }
  const { label, color } = map[status] ?? { label: status, color: '#94a3b8' }
  return (
    <span style={{ background: color + '1a', color, borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>
      {label}
    </span>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, { label: string; color: string }> = {
    major:         { label: 'Major',         color: '#ef4444' },
    minor:         { label: 'Minor',         color: '#f59e0b' },
    informational: { label: 'Info',          color: '#6366f1' },
  }
  const { label, color } = map[severity] ?? { label: severity, color: '#94a3b8' }
  return (
    <span style={{ background: color + '15', color, borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 600, flexShrink: 0 }}>
      {label}
    </span>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

function cardStyle(status: string): React.CSSProperties {
  const borderColor =
    status === 'deviation'    ? '#ef444433' :
    status === 'partial'      ? '#f59e0b33' :
    status === 'conforming'   ? '#22c55e22' :
    'var(--border)'
  return {
    background: 'var(--surface-2)',
    border: `1px solid ${borderColor}`,
    borderRadius: 'var(--radius)',
    padding: '12px 14px',
  }
}

const summaryBar: React.CSSProperties = {
  display: 'flex',
  gap: 0,
  marginTop: 16,
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  overflow: 'hidden',
  background: 'var(--surface-2)',
}

const summaryBox: React.CSSProperties = {
  marginTop: 14,
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '12px 16px',
}

const sectionLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 6,
}

const tabBar: React.CSSProperties = {
  display: 'flex',
  borderBottom: '1px solid var(--border)',
  marginTop: 18,
  gap: 0,
}

const sourcePill: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '2px 10px',
  fontSize: 11,
  color: 'var(--text-muted)',
}

const emptyBox: React.CSSProperties = {
  marginTop: 14,
  padding: '16px 20px',
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  fontSize: 13,
  color: 'var(--text-muted)',
  textAlign: 'center',
}

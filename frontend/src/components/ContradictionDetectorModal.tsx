import { useState } from 'react'
import ConfidenceBar from './ConfidenceBar.tsx'
import type { ContradictionResult, ContradictionItem } from '../types.ts'

interface Props {
  result: ContradictionResult
  onClose: () => void
}

type Tab = 'all' | 'source_vs_source' | 'intra_document'

export default function ContradictionDetectorModal({ result, onClose }: Props) {
  const [tab, setTab] = useState<Tab>('all')

  const { contradictions, source_vs_source, intra_document,
          severity_counts, overall_assessment, sources_analysed, confidence } = result

  const active =
    tab === 'all'              ? contradictions :
    tab === 'source_vs_source' ? source_vs_source :
    intra_document

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 900, maxWidth: '96vw', maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}
      >
        <div className="modal-header" style={{ paddingBottom: 14 }}>
          <h3>Contradiction Detector</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div style={{ overflowY: 'auto', padding: '0 24px 24px', flex: 1 }}>
          {confidence != null && <ConfidenceBar confidence={confidence} />}

          {/* Stat bar */}
          <div style={statBar}>
            <StatChip label="Total" value={contradictions.length} color="var(--text)" />
            <StatChip label="High" value={severity_counts.high} color="#ef4444" />
            <StatChip label="Medium" value={severity_counts.medium} color="#f59e0b" />
            <StatChip label="Low" value={severity_counts.low} color="#6366f1" />
            <StatChip label="Intra-Doc" value={intra_document.length} color="#f97316" />
            <StatChip label="Src vs Src" value={source_vs_source.length} color="#0ea5e9" />
          </div>

          {/* Sources analysed */}
          {sources_analysed.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
              {sources_analysed.map(s => (
                <span key={s} style={sourcePill}>{s}</span>
              ))}
            </div>
          )}

          {/* Overall assessment */}
          {overall_assessment && (
            <div style={assessmentBox}>
              <div style={sectionLabel}>Overall Assessment</div>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text)', lineHeight: 1.6 }}>
                {overall_assessment}
              </p>
            </div>
          )}

          {/* Tab bar */}
          <div style={tabBar}>
            <TabBtn active={tab === 'all'} onClick={() => setTab('all')}
              label={`All (${contradictions.length})`} color="var(--text-muted)" />
            <TabBtn active={tab === 'intra_document'} onClick={() => setTab('intra_document')}
              label={`Intra-Document (${intra_document.length})`} color="#f97316" />
            <TabBtn active={tab === 'source_vs_source'} onClick={() => setTab('source_vs_source')}
              label={`Src vs Src (${source_vs_source.length})`} color="#0ea5e9" />
          </div>

          {/* Cards */}
          {active.length === 0 ? (
            <div style={emptyBox}>No contradictions found in this category.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 14 }}>
              {active.map((item, i) => <ContradictionCard key={i} item={item} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ContradictionCard({ item }: { item: ContradictionItem }) {
  const [open, setOpen] = useState(false)

  const labelA = item.type === 'intra_document'
    ? `${item.source_a} — Statement A`
    : item.source_a
  const labelB = item.type === 'intra_document'
    ? `${item.source_b} — Statement B`
    : item.source_b

  return (
    <div style={cardBorder(item.severity)}>
      {/* Header */}
      <div
        style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer' }}
        onClick={() => setOpen(v => !v)}
      >
        <SeverityBadge severity={item.severity} />
        <TypeBadge type={item.type} />
        <div style={{ flex: 1 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>
            {item.topic}
          </span>
        </div>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
          {open ? '▲' : '▼'}
        </span>
      </div>

      {/* Claim preview (always visible) */}
      <div style={claimRow}>
        <ClaimBox label={labelA} claim={item.claim_a} side="a" />
        <div style={{ display: 'flex', alignItems: 'center', fontSize: 18, color: '#ef4444', flexShrink: 0 }}>
          ⟷
        </div>
        <ClaimBox label={labelB} claim={item.claim_b} side="b" />
      </div>

      {/* Expanded detail */}
      {open && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <DetailRow label="Why these contradict" value={item.explanation} />
          <DetailRow label="Resolution" value={item.resolution} highlight />
        </div>
      )}
    </div>
  )
}

function ClaimBox({ label, claim, side }: { label: string; claim: string; side: 'a' | 'b' }) {
  const color = side === 'a' ? '#0ea5e9' : '#8b5cf6'
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.05em', color, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{
        background: color + '0d',
        border: `1px solid ${color}33`,
        borderRadius: 6,
        padding: '8px 10px',
        fontSize: 13,
        color: 'var(--text)',
        lineHeight: 1.5,
      }}>
        {claim}
      </div>
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
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.5 }}>{value}</div>
    </div>
  )
}

function SeverityBadge({ severity: rawSeverity }: { severity: string }) {
  const severity = rawSeverity === 'moderate' ? 'medium' : rawSeverity
  const map: Record<string, { label: string; color: string }> = {
    high:   { label: 'High',   color: '#ef4444' },
    medium: { label: 'Medium', color: '#f59e0b' },
    low:    { label: 'Low',    color: '#6366f1' },
  }
  const { label, color } = map[severity] ?? { label: rawSeverity, color: '#94a3b8' }
  return (
    <span style={{ background: color + '1a', color, borderRadius: 4,
      padding: '2px 8px', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>
      {label}
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  const map: Record<string, { label: string; color: string }> = {
    source_vs_source: { label: 'Source vs Source', color: '#0ea5e9' },
    intra_document:   { label: 'Intra-Document',   color: '#f97316' },
  }
  const { label, color } = map[type] ?? { label: type, color: '#94a3b8' }
  return (
    <span style={{ background: color + '15', color, borderRadius: 4,
      padding: '2px 8px', fontSize: 11, fontWeight: 600, flexShrink: 0 }}>
      {label}
    </span>
  )
}

function StatChip({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '10px 14px', flex: 1 }}>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{label}</div>
    </div>
  )
}

function TabBtn({ active, onClick, label, color }: {
  active: boolean; onClick: () => void; label: string; color: string
}) {
  return (
    <button onClick={onClick} style={{
      background: 'none', border: 'none',
      borderBottom: active ? `2px solid ${color}` : '2px solid transparent',
      padding: '8px 14px', fontSize: 13,
      fontWeight: active ? 600 : 400,
      color: active ? color : 'var(--text-muted)',
      cursor: 'pointer', transition: 'color 0.15s',
    }}>
      {label}
    </button>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

function cardBorder(severity: string): React.CSSProperties {
  const color =
    severity === 'high'   ? '#ef444433' :
    severity === 'medium' ? '#f59e0b33' :
    '#6366f122'
  return {
    background: 'var(--surface-2)',
    border: `1px solid ${color}`,
    borderRadius: 'var(--radius)',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  }
}

const statBar: React.CSSProperties = {
  display: 'flex',
  marginTop: 16,
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  overflow: 'hidden',
  background: 'var(--surface-2)',
}

const sourcePill: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '2px 10px',
  fontSize: 11,
  color: 'var(--text-muted)',
}

const assessmentBox: React.CSSProperties = {
  marginTop: 14,
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '12px 16px',
}

const sectionLabel: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, letterSpacing: '0.06em',
  textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6,
}

const tabBar: React.CSSProperties = {
  display: 'flex',
  borderBottom: '1px solid var(--border)',
  marginTop: 18,
}

const claimRow: React.CSSProperties = {
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
  marginTop: 8,
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

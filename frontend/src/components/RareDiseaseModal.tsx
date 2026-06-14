import { useState } from 'react'
import type { RareDiseaseResult, RareDisease, MappedSymptom } from '../types.ts'

interface Props {
  result: RareDiseaseResult
  onClose: () => void
}

export default function RareDiseaseModal({ result, onClose }: Props) {
  const { symptoms_mapped, diseases } = result
  const [selected, setSelected] = useState<RareDisease | null>(diseases[0] ?? null)
  const [showAllSymptoms, setShowAllSymptoms] = useState(false)

  const mappedCount = symptoms_mapped.filter(s => s.hpo_id).length
  const displaySymptoms = showAllSymptoms ? symptoms_mapped : symptoms_mapped.slice(0, 6)

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 860, maxWidth: '96vw', maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}
      >
        <div className="modal-header" style={{ paddingBottom: 14 }}>
          <h3>Rare Disease Finder</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div style={{ overflowY: 'auto', padding: '0 24px 24px', flex: 1 }}>

          {/* Symptom → HPO mapping */}
          <section style={{ marginTop: 16 }}>
            <div style={sectionLabel}>
              Extracted Symptoms
              <span style={countBadge}>{mappedCount} / {symptoms_mapped.length} mapped to HPO</span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {displaySymptoms.map((s, i) => <SymptomChip key={i} s={s} />)}
            </div>
            {symptoms_mapped.length > 6 && (
              <button
                style={toggleBtn}
                onClick={() => setShowAllSymptoms(v => !v)}
              >
                {showAllSymptoms ? 'Show less' : `Show all ${symptoms_mapped.length} symptoms`}
              </button>
            )}
          </section>

          {/* No diseases */}
          {diseases.length === 0 && (
            <div style={emptyBox}>
              No rare diseases found for the extracted symptom profile. Try adding more clinical details.
            </div>
          )}

          {/* Two-column layout: list + detail */}
          {diseases.length > 0 && (
            <div style={{ display: 'flex', gap: 14, marginTop: 20, alignItems: 'flex-start' }}>

              {/* Disease list */}
              <div style={{ width: 280, flexShrink: 0 }}>
                <div style={sectionLabel}>
                  Top Matches
                  <span style={countBadge}>{diseases.length}</span>
                </div>
                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
                  {diseases.map((d, i) => (
                    <button
                      key={d.orpha_code}
                      onClick={() => setSelected(d)}
                      style={listItem(d === selected, i === diseases.length - 1)}
                    >
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 6 }}>
                        <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', lineHeight: 1.4, flex: 1 }}>
                          {d.name}
                        </span>
                        <MatchBadge score={d.match_score} count={d.matched_hpo_count} total={d.total_queried} />
                      </div>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2, display: 'block' }}>
                        {d.orpha_code}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Detail panel */}
              {selected && (
                <div style={{ flex: 1 }}>
                  <div style={sectionLabel}>Disease Detail</div>
                  <div style={detailCard}>
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', lineHeight: 1.4 }}>
                        {selected.name}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>
                        {selected.orpha_code}
                      </div>
                    </div>

                    {/* Match score bar */}
                    <div style={{ marginBottom: 14 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          HPO Match Score
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: matchColor(selected.match_score) }}>
                          {selected.matched_hpo_count} / {selected.total_queried} symptoms
                          ({Math.round(selected.match_score * 100)}%)
                        </span>
                      </div>
                      <div style={progressTrack}>
                        <div style={progressFill(selected.match_score)} />
                      </div>
                    </div>

                    {/* Matched symptoms */}
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 8 }}>
                        Matching Symptom Terms
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {selected.matched_symptoms.map((m, i) => (
                          <div key={i} style={matchedSymptomRow}>
                            <span style={hpoTag}>{m.hpo_id}</span>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500 }}>{m.symptom}</div>
                              {m.hpo_name && m.hpo_name !== m.symptom && (
                                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>
                                  HPO: {m.hpo_name}
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SymptomChip({ s }: { s: MappedSymptom }) {
  const mapped = !!s.hpo_id
  return (
    <span
      title={mapped ? `${s.hpo_id} — ${s.hpo_name}` : 'No HPO match found'}
      style={{
        background: mapped ? '#6366f11a' : 'var(--surface-2)',
        color: mapped ? '#818cf8' : 'var(--text-muted)',
        border: `1px solid ${mapped ? '#6366f133' : 'var(--border)'}`,
        borderRadius: 4,
        padding: '3px 9px',
        fontSize: 12,
        fontWeight: 500,
        cursor: 'default',
      }}
    >
      {s.symptom}
      {mapped && <span style={{ marginLeft: 4, opacity: 0.6, fontSize: 10 }}>✓</span>}
    </span>
  )
}

function MatchBadge({ score, count, total }: { score: number; count: number; total: number }) {
  const color = matchColor(score)
  return (
    <span style={{
      background: color + '1a',
      color,
      borderRadius: 4,
      padding: '2px 6px',
      fontSize: 10,
      fontWeight: 700,
      flexShrink: 0,
      whiteSpace: 'nowrap',
    }}>
      {count}/{total}
    </span>
  )
}

// ── Style helpers ─────────────────────────────────────────────────────────────

function matchColor(score: number): string {
  if (score >= 0.6) return '#22c55e'
  if (score >= 0.35) return '#f59e0b'
  return '#94a3b8'
}

function listItem(active: boolean, last: boolean): React.CSSProperties {
  return {
    display: 'block',
    width: '100%',
    textAlign: 'left',
    background: active ? 'var(--accent)0f' : 'transparent',
    borderBottom: last ? 'none' : '1px solid var(--border)',
    borderLeft: active ? '3px solid var(--accent)' : '3px solid transparent',
    padding: '9px 12px',
    cursor: 'pointer',
    transition: 'background 0.1s',
  }
}

const sectionLabel: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 8,
}

const countBadge: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '1px 7px',
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-muted)',
}

const emptyBox: React.CSSProperties = {
  marginTop: 20,
  padding: '16px 20px',
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  fontSize: 13,
  color: 'var(--text-muted)',
  textAlign: 'center',
}

const detailCard: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '16px 18px',
}

const matchedSymptomRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: 10,
  padding: '7px 10px',
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 6,
}

const hpoTag: React.CSSProperties = {
  background: '#6366f11a',
  color: '#818cf8',
  border: '1px solid #6366f133',
  borderRadius: 4,
  padding: '1px 6px',
  fontSize: 10,
  fontWeight: 600,
  flexShrink: 0,
  whiteSpace: 'nowrap',
}

const progressTrack: React.CSSProperties = {
  height: 6,
  background: 'var(--border)',
  borderRadius: 3,
  overflow: 'hidden',
}

function progressFill(score: number): React.CSSProperties {
  return {
    height: '100%',
    width: `${Math.round(score * 100)}%`,
    background: matchColor(score),
    borderRadius: 3,
    transition: 'width 0.3s',
  }
}

const toggleBtn: React.CSSProperties = {
  marginTop: 8,
  background: 'none',
  border: 'none',
  color: 'var(--accent)',
  fontSize: 12,
  cursor: 'pointer',
  padding: 0,
}

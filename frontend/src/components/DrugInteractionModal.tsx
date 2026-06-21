import ReactMarkdown from 'react-markdown'
import ConfidenceBar from './ConfidenceBar.tsx'
import type { DrugInteractionResult, DrugInteraction, PICOResult } from '../types.ts'

interface Props {
  result: DrugInteractionResult
  onClose: () => void
}

export default function DrugInteractionModal({ result, onClose }: Props) {
  const { query_response, interaction_results, confidence } = result

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 760, maxWidth: '94vw', maxHeight: '88vh', display: 'flex', flexDirection: 'column' }}
      >
        <div className="modal-header" style={{ paddingBottom: 14 }}>
          <h3>Drug Interaction Analysis</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div style={{ overflowY: 'auto', padding: '0 40px 20px', flex: 1 }}>
          {confidence != null && <ConfidenceBar confidence={confidence} />}

          {query_response && (
            <Section title="Clinical Summary">
              <div style={markdownBody}><ReactMarkdown>{query_response}</ReactMarkdown></div>
            </Section>
          )}

          {interaction_results?.length > 0 && (
            <Section title="Drug Pairs">
              {interaction_results.map((pair: DrugInteraction, i: number) => (
                <div key={i} style={cardStyle}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <strong style={{ fontSize: 14 }}>
                      {pair.drug1} ↔ {pair.drug2}
                    </strong>
                    <span style={severityBadge(pair.severity)}>{pair.severity}</span>
                  </div>

                  {pair.rxnorm_description && (
                    <p style={mutedText}><span style={{ fontWeight: 500 }}>RxNorm: </span>{pair.rxnorm_description}</p>
                  )}
                  {pair.openfda_boxed_warning && (
                    <p style={{ ...mutedText, marginTop: 4, color: '#ef4444' }}>
                      <span style={{ fontWeight: 500 }}>⚠ Boxed Warning: </span>{pair.openfda_boxed_warning}
                    </p>
                  )}
                  {pair.openfda_warnings && (
                    <p style={{ ...mutedText, marginTop: 4 }}>
                      <span style={{ fontWeight: 500 }}>FDA Warnings: </span>{pair.openfda_warnings}
                    </p>
                  )}
                  {pair.adverse_event_count != null && (
                    <p style={{ ...mutedText, marginTop: 4 }}>
                      <span style={{ fontWeight: 500 }}>Adverse event reports: </span>{pair.adverse_event_count}
                    </p>
                  )}

                  {pair.pico && <PICOCard pico={pair.pico} />}
                </div>
              ))}
            </Section>
          )}

        </div>
      </div>
    </div>
  )
}

function PICOCard({ pico }: { pico: PICOResult }) {
  return (
    <div style={{ marginTop: 10, padding: '8px 12px', background: 'var(--surface-1)', borderRadius: 'var(--radius)', borderLeft: '3px solid var(--accent)' }}>
      <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>
        Evidence (PICO) · {pico.evidence_quality}
      </p>
      {pico.population && <p style={picoRow}><span style={{ fontWeight: 500 }}>Population: </span>{pico.population}</p>}
      {pico.intervention && <p style={picoRow}><span style={{ fontWeight: 500 }}>Intervention: </span>{pico.intervention}</p>}
      {pico.comparison && <p style={picoRow}><span style={{ fontWeight: 500 }}>Comparison: </span>{pico.comparison}</p>}
      {pico.outcome && <p style={picoRow}><span style={{ fontWeight: 500 }}>Outcome: </span>{pico.outcome}</p>}
      {pico.key_findings && <p style={{ ...picoRow, marginTop: 6, fontStyle: 'italic' }}>{pico.key_findings}</p>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 20 }}>
      <h4 style={{
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.06em',
        textTransform: 'uppercase' as const,
        color: 'var(--text-muted)',
        marginBottom: 10,
      }}>
        {title}
      </h4>
      {children}
    </div>
  )
}

const cardStyle: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '10px 14px',
  marginBottom: 8,
}

const mutedText: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-muted)',
  lineHeight: 1.6,
}

const picoRow: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-muted)',
  lineHeight: 1.5,
  marginTop: 2,
}

const markdownBody: React.CSSProperties = {
  fontSize: 14,
  lineHeight: 1.75,
  color: 'var(--text)',
}

function severityBadge(severity: string): React.CSSProperties {
  const color =
    severity === 'HIGH' || severity === 'CONTRAINDICATED' ? '#ef4444'
    : severity === 'MODERATE' ? '#f59e0b'
    : severity === 'LOW' ? '#3b82f6'
    : '#6b7280'
  return {
    background: color + '1a',
    color,
    borderRadius: 4,
    padding: '2px 8px',
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
  }
}

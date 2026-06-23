import ReactMarkdown from 'react-markdown'
import ConfidenceBar from './ConfidenceBar.tsx'
import type { ClinicalAnalysis, PossibleCondition, RedFlag, RecommendedTest } from '../types.ts'

interface Props {
  analysis: ClinicalAnalysis
  onClose: () => void
}

export default function ClinicalAnalysisModal({ analysis, onClose }: Props) {
  const { query_response, symptom_analysis, confidence } = analysis

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 720, maxWidth: '94vw', maxHeight: '88vh', display: 'flex', flexDirection: 'column' }}
      >
        <div className="modal-header" style={{ paddingBottom: 14 }}>
          <h3>Clinical Analysis</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div style={{ overflowY: 'auto', padding: '0 40px 20px', flex: 1 }}>
          {confidence != null && <ConfidenceBar confidence={confidence} />}

          {query_response && (
            <Section title="Clinical Summary">
              <div style={markdownBody}><ReactMarkdown>{query_response}</ReactMarkdown></div>
            </Section>
          )}

          {symptom_analysis?.next_best_discriminator && (
            <Section title="Next Best Discriminator">
              <div style={{ ...cardStyle, borderLeft: '3px solid #6366f1' }}>
                <p style={mutedText}>{symptom_analysis.next_best_discriminator}</p>
              </div>
            </Section>
          )}

          {symptom_analysis?.possible_conditions?.length > 0 && (
            <Section title="Possible Conditions">
              {symptom_analysis.possible_conditions.map((c: PossibleCondition, i: number) => (
                <div key={i} style={cardStyle}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <div>
                      <strong style={{ fontSize: 14 }}>{c.name}</strong>
                      {c.icd11_code && (
                        <span style={{ ...mutedText, fontSize: 11, marginLeft: 8 }}>{c.icd11_code}</span>
                      )}
                    </div>
                    <span style={likelihoodBadge(c.posterior_likelihood)}>{c.posterior_likelihood.replace('_', ' ')}</span>
                  </div>
                  {c.epidemiological_prior && (
                    <p style={{ ...mutedText, marginTop: 2 }}>
                      <span style={{ fontWeight: 500 }}>Prior: </span>{c.epidemiological_prior}
                    </p>
                  )}
                  <p style={{ ...mutedText, marginTop: 4 }}>{c.likelihood_rationale}</p>
                  {c.supporting_evidence?.length > 0 && (
                    <p style={{ ...mutedText, marginTop: 4 }}>
                      <span style={{ fontWeight: 500 }}>Supporting: </span>
                      {c.supporting_evidence.map(e => e.finding).join(' · ')}
                    </p>
                  )}
                  {c.refuting_evidence?.length > 0 && (
                    <p style={{ ...mutedText, marginTop: 2 }}>
                      <span style={{ fontWeight: 500 }}>Against: </span>
                      {c.refuting_evidence.map(e => e.finding).join(' · ')}
                    </p>
                  )}
                  {c.unconfirmed_hallmark_symptoms?.length > 0 && (
                    <p style={{ ...mutedText, marginTop: 4 }}>
                      <span style={{ fontWeight: 500 }}>Unconfirmed hallmarks: </span>
                      {c.unconfirmed_hallmark_symptoms.join(', ')}
                    </p>
                  )}
                </div>
              ))}
            </Section>
          )}

          {symptom_analysis?.red_flags?.length > 0 && (
            <Section title="Red Flags">
              {symptom_analysis.red_flags.map((rf: RedFlag, i: number) => (
                <div key={i} style={{ ...cardStyle, borderLeft: '3px solid #ef4444' }}>
                  <strong style={{ fontSize: 13, color: '#ef4444' }}>⚠ {rf.symptom}</strong>
                  <p style={{ ...mutedText, marginTop: 4 }}>{rf.action}</p>
                  <p style={{ ...mutedText, marginTop: 2 }}>
                    <span style={{ fontWeight: 500 }}>Associated: </span>{rf.associated_condition}
                  </p>
                  {rf.clinical_decision_rule && (
                    <p style={{ ...mutedText, marginTop: 2 }}>
                      <span style={{ fontWeight: 500 }}>Rule: </span>{rf.clinical_decision_rule}
                    </p>
                  )}
                </div>
              ))}
            </Section>
          )}

          {symptom_analysis?.recommended_tests?.length > 0 && (
            <Section title="Recommended Tests">
              {symptom_analysis.recommended_tests.map((t: RecommendedTest, i: number) => (
                <div key={i} style={cardStyle}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <strong style={{ fontSize: 13 }}>{t.test}</strong>
                    <span style={priorityBadge(t.priority)}>{t.priority}</span>
                  </div>
                  <p style={{ ...mutedText, marginTop: 4 }}>{t.diagnostic_value}</p>
                  <p style={{ ...mutedText, marginTop: 2 }}>
                    <span style={{ fontWeight: 500 }}>Targets: </span>{t.targets_condition}
                  </p>
                </div>
              ))}
            </Section>
          )}

        </div>
      </div>
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

const markdownBody: React.CSSProperties = {
  fontSize: 14,
  lineHeight: 1.75,
  color: 'var(--text)',
}

function likelihoodBadge(likelihood: string): React.CSSProperties {
  const color =
    likelihood === 'high' ? '#ef4444'
    : likelihood === 'medium' ? '#f59e0b'
    : likelihood === 'low' ? '#22c55e'
    : '#94a3b8'
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

function priorityBadge(priority: string): React.CSSProperties {
  const color =
    priority === 'stat' ? '#ef4444'
    : priority === 'urgent' ? '#f59e0b'
    : '#64748b'
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

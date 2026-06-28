import { useState } from 'react'
import type { GradedArticle, LiteratureReviewResult } from '../types.ts'

interface Props {
  result: LiteratureReviewResult
  onClose: () => void
}

export default function LiteratureReviewModal({ result, onClose }: Props) {
  const { articles, search_queries } = result
  const query = search_queries?.pubmed?.primary_query ?? ''

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 800, maxWidth: '95vw', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
      >
        <div className="modal-header" style={{ paddingBottom: 14 }}>
          <h3>Literature Review</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div style={{ overflowY: 'auto', padding: '0 24px 24px', flex: 1 }}>

          {/* {query && (
            <div style={queryBox}>
              <span style={queryLabel}>PubMed query</span>
              <code style={{ fontSize: 12, color: 'var(--text)', wordBreak: 'break-all' }}>{query}</code>
            </div>
          )} */}

          {articles.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 20 }}>
              No articles found for this query.
            </div>
          ) : (
            <div style={{ marginTop: 16 }}>
              <div style={sectionLabel}>{articles.length} articles found</div>
              {articles.map((a, i) => (
                <ArticleCard key={a.id ?? i} article={a} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ArticleCard({ article }: { article: GradedArticle }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={cardStyle}>
      {/* Header row */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <span style={gradeBadge(article.grade)}>{article.grade}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.4, marginBottom: 4 }}>
            {article.title || '(No title)'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {[article.source, article.pub_date].filter(Boolean).join(' · ')}
            {article.authors?.length > 0 && (
              <> · {article.authors.slice(0, 3).join(', ')}{article.authors.length > 3 ? ' et al.' : ''}</>
            )}
          </div>
        </div>
      </div>

      {/* Study metadata row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
        <Tag color="var(--accent)">{article.study_type}</Tag>
        {article.sample_size != null && (
          <Tag color="#22c55e">n = {article.sample_size.toLocaleString()}</Tag>
        )}
        {article.bias_flags.map(f => (
          <Tag key={f} color="#f59e0b">{f}</Tag>
        ))}
      </div>

      {/* Summary (always visible) */}
      {article.summary && (
        <p style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.65, marginTop: 10 }}>
          {article.summary}
        </p>
      )}

      {/* Abstract (toggleable) */}
      {article.abstract && article.abstract !== 'No abstract available.' && (
        <div style={{ marginTop: 8 }}>
          <button
            className="btn-ghost"
            style={{ fontSize: 12, color: 'var(--text-muted)', padding: '2px 0' }}
            onClick={() => setExpanded(e => !e)}
          >
            {expanded ? '▲ Hide abstract' : '▼ Show abstract'}
          </button>
          {expanded && (
            <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.65, marginTop: 6 }}>
              {article.abstract}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function Tag({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span style={{
      background: color + '1a',
      color,
      borderRadius: 4,
      padding: '2px 7px',
      fontSize: 11,
      fontWeight: 600,
    }}>
      {children}
    </span>
  )
}

function gradeBadge(grade: string): React.CSSProperties {
  const color = grade === 'A' ? '#22c55e' : grade === 'B' ? '#3b82f6' : grade === 'C' ? '#f59e0b' : '#ef4444'
  return {
    background: color + '1a',
    color,
    border: `1px solid ${color}33`,
    borderRadius: 6,
    padding: '3px 9px',
    fontSize: 13,
    fontWeight: 700,
    flexShrink: 0,
    fontFamily: 'monospace',
  }
}

const cardStyle: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '12px 14px',
  marginBottom: 10,
}

const queryBox: React.CSSProperties = {
  marginTop: 16,
  padding: '10px 14px',
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
}

const queryLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  letterSpacing: '0.07em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
}

const sectionLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 10,
}

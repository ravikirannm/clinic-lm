import { useEffect, useState } from 'react'
import type { ICD11Match, ICD11TreeNode } from '../types.ts'

interface Props {
  result: { icd11_results: ICD11Match[] }
  onClose: () => void
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

export default function ICD11Modal({ result, onClose }: Props) {
  const { icd11_results } = result
  const [selectedCode, setSelectedCode] = useState<string>(icd11_results[0]?.code ?? '')
  const [treeKey, setTreeKey] = useState(0)
  const isMobile = useIsMobile()

  const selectedMatch = icd11_results.find(r => r.code === selectedCode) ?? null
  const tree = selectedMatch?.tree ?? null

  const handleCodeChange = (code: string) => {
    setSelectedCode(code)
    setTreeKey(k => k + 1)
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 760, maxWidth: '94vw', maxHeight: '88vh', display: 'flex', flexDirection: 'column' }}
      >
        {/* Header */}
        <div className="modal-header" style={{ paddingBottom: 12 }}>
          <div>
            <h3 style={{ margin: 0 }}>ICD-11 Classification</h3>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3, letterSpacing: '0.02em' }}>
              WHO International Classification of Diseases · 11th Revision
            </div>
          </div>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        {/* Condition selector */}
        {icd11_results.length > 0 && (
          <div style={{ padding: '0 24px 14px', borderBottom: '1px solid var(--border)' }}>
            <div style={sectionLabelStyle}>Matched conditions</div>
            {icd11_results.length <= 5 || isMobile ? (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {icd11_results.map(m => (
                  <button
                    key={m.code}
                    className={`icd-pill-btn${selectedCode === m.code ? ' active' : ''}`}
                    onClick={() => handleCodeChange(m.code)}
                  >
                    <span style={{
                      fontSize: 10,
                      fontFamily: 'monospace',
                      background: selectedCode === m.code ? 'rgba(255,255,255,0.22)' : 'var(--accent)1a',
                      color: selectedCode === m.code ? '#fff' : 'var(--accent)',
                      padding: '1px 5px',
                      borderRadius: 3,
                      fontWeight: 700,
                    }}>
                      {m.code}
                    </span>
                    {m.title}
                  </button>
                ))}
              </div>
            ) : (
              <select
                value={selectedCode}
                onChange={e => handleCodeChange(e.target.value)}
                style={selectStyle}
              >
                {icd11_results.map(m => (
                  <option key={m.code} value={m.code}>
                    {m.code} · {m.title}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        {/* Tree */}
        <div style={{ overflowY: 'auto', padding: '20px 24px 24px', flex: 1 }}>
          {selectedCode && (
            <div key={treeKey} className="icd-fade-in">
              {!tree ? (
                <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-muted)' }}>
                  <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.5 }}>🔍</div>
                  <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 6 }}>Tree not available</div>
                  <div style={{ fontSize: 12, maxWidth: 300, margin: '0 auto', lineHeight: 1.6 }}>
                    WHO credentials not configured or this code was not found in the WHO database.
                  </div>
                </div>
              ) : (
                <>
                  {/* Ancestor breadcrumb */}
                  {tree.ancestors && tree.ancestors.length > 0 && (
                    <div style={{ marginBottom: 16 }}>
                      <div style={sectionLabelStyle}>Classification path</div>
                      <div style={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: 6,
                        alignItems: 'center',
                        padding: '12px 16px',
                        background: 'var(--surface-2)',
                        borderRadius: 8,
                        border: '1px solid var(--border)',
                        lineHeight: 1.8,
                      }}>
                        {tree.ancestors.map((a, i) => (
                          <span key={a.entity_id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ fontSize: 13, color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                              {a.code && (
                                <span style={{ ...codeBadgeStyle, fontSize: 11, padding: '2px 7px' }}>{a.code}</span>
                              )}
                              {a.title}
                            </span>
                            <ChevronRight accent={i === tree.ancestors!.length - 1} />
                          </span>
                        ))}
                        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}>
                          {tree.title}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Root node */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '13px 16px',
                    background: 'var(--accent)08',
                    border: '1px solid var(--accent)30',
                    borderLeft: '4px solid var(--accent)',
                    borderRadius: 10,
                    marginBottom: 14,
                  }}>
                    <span style={{ ...codeBadgeStyle, fontSize: 13, padding: '3px 9px' }}>
                      {tree.code}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>
                        {tree.title}
                      </div>
                    </div>
                    {tree.children.length > 0 && (
                      <span style={{
                        fontSize: 11,
                        color: 'var(--text-muted)',
                        background: 'var(--surface)',
                        padding: '3px 9px',
                        borderRadius: 10,
                        border: '1px solid var(--border)',
                        flexShrink: 0,
                        whiteSpace: 'nowrap',
                      }}>
                        {tree.children.length} {tree.children.length === 1 ? 'subcategory' : 'subcategories'}
                      </span>
                    )}
                  </div>

                  {/* Children */}
                  {tree.children.length > 0 ? (
                    <div style={{ paddingTop: 2 }}>
                      {tree.children.map((child, i) => (
                        <TreeNode
                          key={child.entity_id}
                          node={child}
                          isLast={i === tree.children.length - 1}
                        />
                      ))}
                    </div>
                  ) : (
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '12px 16px',
                      background: 'var(--surface-2)',
                      borderRadius: 8,
                      fontSize: 13,
                      color: 'var(--text-muted)',
                    }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--border)', display: 'block', flexShrink: 0 }} />
                      Leaf node — no subcategories
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── SVG primitives ────────────────────────────────────────────────────────────

function ChevronRight({ accent = false }: { accent?: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, display: 'block' }}>
      <path
        d="M 5 3 L 11 8 L 5 13"
        stroke={accent ? 'var(--accent)' : 'var(--text-muted)'}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={accent ? 0.55 : 0.35}
      />
    </svg>
  )
}

// ── Tree node ─────────────────────────────────────────────────────────────────

interface TreeNodeProps {
  node: ICD11TreeNode
  depth?: number
  isLast?: boolean
}

function TreeNode({ node, depth = 0, isLast = false }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [visible, setVisible] = useState(false)

  const hasPreloadedChildren = node.children.length > 0
  const isDepthLimit = node.has_children && !hasPreloadedChildren

  const toggle = () => {
    if (!node.has_children) return
    if (!expanded) {
      setMounted(true)
      setExpanded(true)
      requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)))
    } else {
      setVisible(false)
      setTimeout(() => {
        setMounted(false)
        setExpanded(false)
      }, 180)
    }
  }

  return (
    <div style={{ position: 'relative', paddingLeft: 28 }}>
      {/* Vertical connector line (div — adapts to full node height including children) */}
      <div style={{
        position: 'absolute',
        left: 8,
        top: 0,
        height: isLast ? 16 : '100%',
        width: 1.5,
        background: 'var(--border)',
        pointerEvents: 'none',
      }} />

      {/* Horizontal line + filled arrowhead */}
      <svg
        width="28"
        height="32"
        viewBox="0 0 28 32"
        style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible', pointerEvents: 'none' }}
      >
        {/* Line: from vertical bar up to where arrowhead base starts */}
        <line
          x1="9" y1="16"
          x2="18" y2="16"
          className="icd-connector-line"
          stroke="var(--border)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeDasharray={9}
          strokeDashoffset={9}
        />
        {/* Filled triangle arrowhead pointing right */}
        <polygon
          points="18,12 26,16 18,20"
          className="icd-connector-arrow"
          fill="var(--accent)"
          opacity="0.0"
        />
      </svg>

      {/* Node row */}
      <div
        onClick={toggle}
        className={`icd-tree-node-row${node.has_children ? ' icd-clickable' : ''}`}
        style={{ marginBottom: 1 }}
      >
        {node.has_children ? (
          <svg
            className={`icd-chevron${expanded ? ' expanded' : ''}`}
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
          >
            <path
              d="M 2.5 2 L 9 6 L 2.5 10"
              stroke="var(--accent)"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0 }}>
            <circle cx="6" cy="6" r="2.5" fill="var(--border)" />
          </svg>
        )}

        {node.code && <span style={codeBadgeStyle}>{node.code}</span>}

        <span style={{ fontSize: 13, color: 'var(--text)', fontWeight: expanded ? 500 : 400 }}>
          {node.title || node.entity_id}
        </span>

        {node.has_children && !expanded && node.children.length > 0 && (
          <span style={{
            fontSize: 10,
            color: 'var(--text-muted)',
            marginLeft: 'auto',
            flexShrink: 0,
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            padding: '1px 6px',
          }}>
            {node.children.length}
          </span>
        )}
      </div>

      {mounted && (
        <div className={`icd-children${visible ? ' visible' : ''}`}>
          {isDepthLimit ? (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '4px 0 4px 4px' }}>
              Further subcategories not pre-loaded.
            </div>
          ) : (
            node.children.map((child, i) => (
              <TreeNode
                key={child.entity_id}
                node={child}
                depth={depth + 1}
                isLast={i === node.children.length - 1}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const selectStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  fontSize: 13,
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  color: 'var(--text)',
}

const sectionLabelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 8,
}


const codeBadgeStyle: React.CSSProperties = {
  background: 'var(--accent)1a',
  color: 'var(--accent)',
  borderRadius: 4,
  padding: '2px 7px',
  fontSize: 11,
  fontWeight: 700,
  fontFamily: 'monospace',
  flexShrink: 0,
  letterSpacing: '0.02em',
}

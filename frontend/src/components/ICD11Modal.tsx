import { useState } from 'react'
import type { ICD11Match, ICD11TreeNode } from '../types.ts'

interface Props {
  result: { icd11_results: ICD11Match[] }
  onClose: () => void
}

export default function ICD11Modal({ result, onClose }: Props) {
  const { icd11_results } = result
  const [selectedCode, setSelectedCode] = useState<string>(icd11_results[0]?.code ?? '')

  const selectedMatch = icd11_results.find(r => r.code === selectedCode) ?? null
  const tree = selectedMatch?.tree ?? null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        style={{ width: 760, maxWidth: '94vw', maxHeight: '88vh', display: 'flex', flexDirection: 'column' }}
      >
        <div className="modal-header" style={{ paddingBottom: 14 }}>
          <h3>ICD-11 Classification Tree</h3>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>

        <div style={{ overflowY: 'auto', padding: '0 24px 24px', flex: 1 }}>

          {/* Dropdown */}
          <div style={{ marginTop: 16 }}>
            <label style={labelStyle}>Select matched condition</label>
            <select
              value={selectedCode}
              onChange={e => setSelectedCode(e.target.value)}
              style={selectStyle}
            >
              <option value="">— choose —</option>
              {icd11_results.map(m => (
                <option key={m.code} value={m.code}>
                  {m.code} · {m.title}
                </option>
              ))}
            </select>
          </div>

          {/* Tree area */}
          {selectedCode && (
            <div style={{ marginTop: 20 }}>
              {!tree ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                  Tree not available for this code (WHO credentials not configured or code not found in WHO database).
                </div>
              ) : (
                <>
                  {/* Ancestors breadcrumb */}
                  {tree.ancestors && tree.ancestors.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 12, alignItems: 'center' }}>
                      {tree.ancestors.map((a, i) => (
                        <span key={a.entity_id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 3 }}>
                            {a.code && <span style={codeBadgeStyle}>{a.code}</span>}
                            {a.title}
                          </span>
                          {i < tree.ancestors!.length - 1 && (
                            <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>›</span>
                          )}
                        </span>
                      ))}
                      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>›</span>
                    </div>
                  )}

                  {/* Root node */}
                  <div style={rootNodeStyle}>
                    <span style={{ ...codeBadgeStyle, fontSize: 13, padding: '2px 8px' }}>{tree.code}</span>
                    <span style={{ fontSize: 15, fontWeight: 600 }}>{tree.title}</span>
                  </div>

                  {/* Children tree */}
                  {tree.children && tree.children.length > 0 ? (
                    <div style={{ marginTop: 8, borderLeft: '2px solid var(--border)', paddingLeft: 12 }}>
                      {tree.children.map(child => (
                        <TreeNode key={child.entity_id} node={child} />
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>
                      Leaf node — no subcategories.
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

// ── Tree node (pure expand/collapse — all data pre-loaded) ───────────────────

interface TreeNodeProps {
  node: ICD11TreeNode
  depth?: number
}

function TreeNode({ node, depth = 0 }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(false)
  const hasPreloadedChildren = node.children.length > 0
  const isDepthLimit = node.has_children && !hasPreloadedChildren

  return (
    <div style={{ paddingLeft: depth > 0 ? 16 : 0 }}>
      <div
        onClick={() => node.has_children && setExpanded(e => !e)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 0',
          cursor: node.has_children ? 'pointer' : 'default',
        }}
      >
        <span style={{ fontSize: 10, color: 'var(--text-muted)', width: 12, flexShrink: 0 }}>
          {node.has_children ? (expanded ? '▼' : '▶') : '·'}
        </span>
        {node.code && <span style={codeBadgeStyle}>{node.code}</span>}
        <span style={{ fontSize: 13, color: 'var(--text)' }}>{node.title || node.entity_id}</span>
      </div>

      {expanded && (
        <div style={{ borderLeft: '1px solid var(--border)', paddingLeft: 12, marginLeft: 6 }}>
          {isDepthLimit ? (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '4px 0' }}>
              Further subcategories not pre-loaded.
            </div>
          ) : (
            node.children.map(child => (
              <TreeNode key={child.entity_id} node={child} depth={depth + 1} />
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 6,
}

const selectStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  fontSize: 13,
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  color: 'var(--text)',
}

const codeBadgeStyle: React.CSSProperties = {
  background: 'var(--accent)1a',
  color: 'var(--accent)',
  borderRadius: 4,
  padding: '1px 6px',
  fontSize: 11,
  fontWeight: 600,
  fontFamily: 'monospace',
  flexShrink: 0,
}

const rootNodeStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  padding: '10px 14px',
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
}

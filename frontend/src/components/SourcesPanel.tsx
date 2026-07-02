import { useState } from 'react'
import AddSourceModal from './AddSourceModal.tsx'
import type { AddSourceData, Source } from '../types.ts'

interface Props {
  sources: Source[]
  onAddSource: (data: AddSourceData, onProgress: (step: string, pct: number) => void) => Promise<void>
  className?: string
}

export default function SourcesPanel({ sources, onAddSource, className }: Props) {
  const [showModal, setShowModal] = useState(false)

  return (
    <aside className={`panel-left${className ? ` ${className}` : ''}`}>
      <div className="panel-section-title">Sources</div>

      <div className="source-list">
        {sources.length === 0 && (
          <p style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 13 }}>
            No sources yet.
          </p>
        )}
        {sources.map(src => (
          <div key={src.id} className="source-item">
            <span className="source-item-icon">
              {src.type === 'pdf' ? '📄'
                : src.type === 'docx' ? '📝'
                : src.type === 'image' ? '🖼️'
                : src.type === 'url' ? '🔗'
                : '📋'}
            </span>
            <span className="source-item-name" title={src.name}>{src.name}</span>
          </div>
        ))}
      </div>

      <div className="panel-left-footer">
        <button className="btn-add-source" onClick={() => setShowModal(true)}>
          + Add source
        </button>
      </div>

      {showModal && (
        <AddSourceModal
          onClose={() => setShowModal(false)}
          onSubmit={async (data, onProgress) => {
            await onAddSource(data, onProgress)
            setShowModal(false)
          }}
        />
      )}
    </aside>
  )
}

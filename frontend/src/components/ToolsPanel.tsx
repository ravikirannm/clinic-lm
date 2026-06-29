import { useEffect, useState } from 'react'
import ClinicalAnalysisModal from './ClinicalAnalysisModal.tsx'
import DrugInteractionModal from './DrugInteractionModal.tsx'
import ICD11Modal from './ICD11Modal.tsx'
import LiteratureReviewModal from './LiteratureReviewModal.tsx'
import RiskAnalysisModal from './RiskAnalysisModal.tsx'
import RareDiseaseModal from './RareDiseaseModal.tsx'
import GuidelinesConformanceModal from './GuidelinesConformanceModal.tsx'
import ContradictionDetectorModal from './ContradictionDetectorModal.tsx'
import DocumentDrafterModal from './DocumentDrafterModal.tsx'
import type { ClinicalAnalysis, DrugInteractionResult, ICD11Result, LiteratureReviewResult, RiskAnalysisResult, RareDiseaseResult, GuidelinesConformanceResult, ContradictionResult, DraftResult } from '../types.ts'

interface Props {
  notebookId: string
  className?: string
}

type Status = 'idle' | 'running' | 'done'

export default function ToolsPanel({ notebookId, className }: Props) {
  const [analysisStatus, setAnalysisStatus] = useState<Status>('idle')
  const [analysis, setAnalysis] = useState<ClinicalAnalysis | null>(null)
  const [showAnalysisModal, setShowAnalysisModal] = useState(false)

  const [interactionStatus, setInteractionStatus] = useState<Status>('idle')
  const [interactions, setInteractions] = useState<DrugInteractionResult | null>(null)
  const [showInteractionModal, setShowInteractionModal] = useState(false)

  const [icd11Status, setIcd11Status] = useState<Status>('idle')
  const [icd11Result, setIcd11Result] = useState<ICD11Result | null>(null)
  const [showIcd11Modal, setShowIcd11Modal] = useState(false)

  const [litStatus, setLitStatus] = useState<Status>('idle')
  const [litResult, setLitResult] = useState<LiteratureReviewResult | null>(null)
  const [showLitModal, setShowLitModal] = useState(false)

  const [riskStatus, setRiskStatus] = useState<Status>('idle')
  const [riskResult, setRiskResult] = useState<RiskAnalysisResult | null>(null)
  const [showRiskModal, setShowRiskModal] = useState(false)

  const [rareStatus, setRareStatus] = useState<Status>('idle')
  const [rareResult, setRareResult] = useState<RareDiseaseResult | null>(null)
  const [showRareModal, setShowRareModal] = useState(false)

  const [guidelinesStatus, setGuidelinesStatus] = useState<Status>('idle')
  const [guidelinesResult, setGuidelinesResult] = useState<GuidelinesConformanceResult | null>(null)
  const [showGuidelinesModal, setShowGuidelinesModal] = useState(false)

  const [contradictionStatus, setContradictionStatus] = useState<Status>('idle')
  const [contradictionResult, setContradictionResult] = useState<ContradictionResult | null>(null)
  const [showContradictionModal, setShowContradictionModal] = useState(false)

  const [draftStatus, setDraftStatus] = useState<Status>('idle')
  const [drafts, setDrafts] = useState<DraftResult>({})
  const [showDraftModal, setShowDraftModal] = useState(false)

  useEffect(() => {
    if (!notebookId) return

    fetch(`/api/notebooks/${notebookId}/analysis`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { setAnalysis(data); setAnalysisStatus('done') } })
      .catch(() => {})

    fetch(`/api/notebooks/${notebookId}/interactions`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { setInteractions(data); setInteractionStatus('done') } })
      .catch(() => {})

    fetch(`/api/notebooks/${notebookId}/icd11`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { setIcd11Result(data); setIcd11Status('done') } })
      .catch(() => {})

    fetch(`/api/notebooks/${notebookId}/literature`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { setLitResult(data); setLitStatus('done') } })
      .catch(() => {})

    fetch(`/api/notebooks/${notebookId}/risk`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { setRiskResult(data); setRiskStatus('done') } })
      .catch(() => {})

    fetch(`/api/notebooks/${notebookId}/rare-diseases`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { setRareResult(data); setRareStatus('done') } })
      .catch(() => {})

    fetch(`/api/notebooks/${notebookId}/guidelines`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { setGuidelinesResult(data); setGuidelinesStatus('done') } })
      .catch(() => {})

    fetch(`/api/notebooks/${notebookId}/contradictions`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { setContradictionResult(data); setContradictionStatus('done') } })
      .catch(() => {})

    fetch(`/api/notebooks/${notebookId}/draft`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { setDrafts(data); setDraftStatus('done') } })
      .catch(() => {})
  }, [notebookId])

  async function handleRunAnalysis() {
    setAnalysisStatus('running')
    try {
      const res = await fetch(`/api/notebooks/${notebookId}/analyze`, { method: 'POST', credentials: 'include' })
      if (!res.ok) { alert((await res.json()).error ?? 'Analysis failed'); setAnalysisStatus('idle'); return }
      setAnalysis(await res.json())
      setAnalysisStatus('done')
    } catch { setAnalysisStatus('idle') }
  }

  async function handleRunInteractions() {
    setInteractionStatus('running')
    try {
      const res = await fetch(`/api/notebooks/${notebookId}/interactions`, { method: 'POST', credentials: 'include' })
      if (!res.ok) { alert((await res.json()).error ?? 'Drug interaction check failed'); setInteractionStatus('idle'); return }
      setInteractions(await res.json())
      setInteractionStatus('done')
    } catch { setInteractionStatus('idle') }
  }

  async function handleRunRisk() {
    setRiskStatus('running')
    try {
      const res = await fetch(`/api/notebooks/${notebookId}/risk`, { method: 'POST', credentials: 'include' })
      if (!res.ok) { alert((await res.json()).error ?? 'Risk analysis failed'); setRiskStatus('idle'); return }
      setRiskResult(await res.json())
      setRiskStatus('done')
    } catch { setRiskStatus('idle') }
  }

  async function handleRunLiterature() {
    setLitStatus('running')
    try {
      const res = await fetch(`/api/notebooks/${notebookId}/literature`, { method: 'POST', credentials: 'include' })
      if (!res.ok) { alert((await res.json()).error ?? 'Literature review failed'); setLitStatus('idle'); return }
      setLitResult(await res.json())
      setLitStatus('done')
    } catch { setLitStatus('idle') }
  }

  async function handleRunContradictions() {
    setContradictionStatus('running')
    try {
      const res = await fetch(`/api/notebooks/${notebookId}/contradictions`, { method: 'POST', credentials: 'include' })
      if (!res.ok) { alert((await res.json()).error ?? 'Contradiction analysis failed'); setContradictionStatus('idle'); return }
      setContradictionResult(await res.json())
      setContradictionStatus('done')
    } catch { setContradictionStatus('idle') }
  }

  async function handleRunGuidelines() {
    setGuidelinesStatus('running')
    try {
      const res = await fetch(`/api/notebooks/${notebookId}/guidelines`, { method: 'POST', credentials: 'include' })
      if (!res.ok) { alert((await res.json()).error ?? 'Guidelines analysis failed'); setGuidelinesStatus('idle'); return }
      setGuidelinesResult(await res.json())
      setGuidelinesStatus('done')
    } catch { setGuidelinesStatus('idle') }
  }

  async function handleRunRareDiseases() {
    setRareStatus('running')
    try {
      const res = await fetch(`/api/notebooks/${notebookId}/rare-diseases`, { method: 'POST', credentials: 'include' })
      if (!res.ok) { alert((await res.json()).error ?? 'Rare disease analysis failed'); setRareStatus('idle'); return }
      setRareResult(await res.json())
      setRareStatus('done')
    } catch { setRareStatus('idle') }
  }

  async function handleRunDraft() {
    setDraftStatus('running')
    try {
      const res = await fetch(`/api/notebooks/${notebookId}/draft`, { method: 'POST', credentials: 'include' })
      if (!res.ok) { alert((await res.json()).error ?? 'Draft generation failed'); setDraftStatus('idle'); return }
      setDrafts(await res.json())
      setDraftStatus('done')
    } catch { setDraftStatus('idle') }
  }

  async function handleRunIcd11() {
    setIcd11Status('running')
    try {
      const res = await fetch(`/api/notebooks/${notebookId}/icd11`, { method: 'POST', credentials: 'include' })
      if (!res.ok) { alert((await res.json()).error ?? 'ICD-11 analysis failed'); setIcd11Status('idle'); return }
      setIcd11Result(await res.json())
      setIcd11Status('done')
    } catch { setIcd11Status('idle') }
  }

  return (
    <aside className={`panel-right${className ? ` ${className}` : ''}`}>
      <div className="panel-section-title">Tools</div>

      <Tool
        label="🔬 Clinical Analysis"
        status={analysisStatus}
        onRun={handleRunAnalysis}
        runningText="Clinical analysis in progress…"
        doneText="View clinical analysis"
        onView={() => setShowAnalysisModal(true)}
      />

      <Tool
        label="💊 Drug Interactions"
        status={interactionStatus}
        onRun={handleRunInteractions}
        runningText="Drug interaction check in progress…"
        doneText="View drug interactions"
        onView={() => setShowInteractionModal(true)}
      />

      <Tool
        label="🌳 ICD-11 Tree"
        status={icd11Status}
        onRun={handleRunIcd11}
        runningText="ICD-11 classification in progress…"
        doneText="View ICD-11 tree"
        onView={() => setShowIcd11Modal(true)}
      />

      <Tool
        label="📚 Literature Review"
        status={litStatus}
        onRun={handleRunLiterature}
        runningText="Literature review in progress…"
        doneText="View literature review"
        onView={() => setShowLitModal(true)}
      />

      <Tool
        label="⚠️ Risk Analysis"
        status={riskStatus}
        onRun={handleRunRisk}
        runningText="Risk analysis in progress…"
        doneText="View risk analysis"
        onView={() => setShowRiskModal(true)}
      />

      <Tool
        label="⚡ Contradiction Detector"
        status={contradictionStatus}
        onRun={handleRunContradictions}
        runningText="Contradiction analysis in progress…"
        doneText="View contradictions"
        onView={() => setShowContradictionModal(true)}
      />

      <Tool
        label="📋 Guidelines Conformance"
        status={guidelinesStatus}
        onRun={handleRunGuidelines}
        runningText="Guidelines analysis in progress…"
        doneText="View guidelines conformance"
        onView={() => setShowGuidelinesModal(true)}
      />

      <Tool
        label="🧬 Rare Disease Finder"
        status={rareStatus}
        onRun={handleRunRareDiseases}
        runningText="Rare disease analysis in progress…"
        doneText="View rare disease matches"
        onView={() => setShowRareModal(true)}
      />

      <Tool
        label="📝 Draft Document"
        status={draftStatus}
        onRun={handleRunDraft}
        runningText="Drafting all documents…"
        doneText="View documents"
        onView={() => setShowDraftModal(true)}
      />

      {showAnalysisModal && analysis && (
        <ClinicalAnalysisModal analysis={analysis} onClose={() => setShowAnalysisModal(false)} />
      )}
      {showInteractionModal && interactions && (
        <DrugInteractionModal result={interactions} onClose={() => setShowInteractionModal(false)} />
      )}
      {showIcd11Modal && icd11Result && (
        <ICD11Modal result={icd11Result} onClose={() => setShowIcd11Modal(false)} />
      )}
      {showLitModal && litResult && (
        <LiteratureReviewModal result={litResult} onClose={() => setShowLitModal(false)} />
      )}
      {showRiskModal && riskResult && (
        <RiskAnalysisModal result={riskResult} onClose={() => setShowRiskModal(false)} />
      )}
      {showRareModal && rareResult && (
        <RareDiseaseModal result={rareResult} onClose={() => setShowRareModal(false)} />
      )}
      {showGuidelinesModal && guidelinesResult && (
        <GuidelinesConformanceModal result={guidelinesResult} onClose={() => setShowGuidelinesModal(false)} />
      )}
      {showContradictionModal && contradictionResult && (
        <ContradictionDetectorModal result={contradictionResult} onClose={() => setShowContradictionModal(false)} />
      )}
      {showDraftModal && Object.keys(drafts).length > 0 && (
        <DocumentDrafterModal drafts={drafts} onClose={() => setShowDraftModal(false)} />
      )}
    </aside>
  )
}

// ── Shared tool row ───────────────────────────────────────────────────────────

interface ToolProps {
  label: string
  status: Status
  onRun: () => void
  runningText: string
  doneText: string
  onView: () => void
}

function Tool({ label, status, onRun, runningText, doneText, onView }: ToolProps) {
  return (
    <>
      <div style={{ padding: '8px 12px' }}>
        <button
          className="btn-primary"
          style={{ width: '100%', fontSize: 13 }}
          onClick={onRun}
          disabled={status === 'running'}
        >
          {label}
        </button>
      </div>

      {status !== 'idle' && (
        <div style={statusBox}>
          {status === 'running' ? (
            <span style={{ color: 'var(--text-muted)' }}>⏳ {runningText}</span>
          ) : (
            <button className="btn-ghost" style={viewBtn} onClick={onView}>
              📋 {doneText}
            </button>
          )}
        </div>
      )}
    </>
  )
}

const statusBox: React.CSSProperties = {
  margin: '0 12px 4px',
  padding: '10px 12px',
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  fontSize: 13,
}

const viewBtn: React.CSSProperties = {
  width: '100%',
  textAlign: 'left',
  color: 'var(--accent)',
  padding: '4px 0',
}

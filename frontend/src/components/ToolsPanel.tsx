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

// ── Animated progress display ─────────────────────────────────────────────────

function ProgressDisplay({ step, target }: { step: string; target: number }) {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const id = setInterval(() => {
      setProgress(prev => {
        if (prev === target) { clearInterval(id); return prev }
        return prev + (prev < target ? 1 : -1)
      })
    }, 20)
    return () => clearInterval(id)
  }, [target])

  return <span style={{ color: 'var(--text-muted)' }}>⏳ {step} ({progress}%)</span>
}

// ── SSE consumer ─────────────────────────────────────────────────────────────

async function consumeSSE(
  url: string,
  onProgress: (step: string, progress: number) => void,
): Promise<unknown> {
  const res = await fetch(url, { method: 'POST', credentials: 'include' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { error?: string }).error ?? 'Request failed')
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: unknown = undefined

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data: ')) continue
      const msg = JSON.parse(line.slice(6)) as {
        type: 'progress' | 'result' | 'error'
        step?: string
        progress?: number
        data?: unknown
        message?: string
      }
      if (msg.type === 'progress') onProgress(msg.step ?? '', msg.progress ?? 0)
      if (msg.type === 'result') result = msg.data
      if (msg.type === 'error') throw new Error(msg.message ?? 'Unknown error')
    }
  }

  return result
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ToolsPanel({ notebookId, className }: Props) {
  const [analysisStatus, setAnalysisStatus] = useState<Status>('idle')
  const [analysisStep, setAnalysisStep] = useState('Starting…')
  const [analysisProgress, setAnalysisProgress] = useState(0)
  const [analysis, setAnalysis] = useState<ClinicalAnalysis | null>(null)
  const [showAnalysisModal, setShowAnalysisModal] = useState(false)

  const [interactionStatus, setInteractionStatus] = useState<Status>('idle')
  const [interactionStep, setInteractionStep] = useState('Starting…')
  const [interactionProgress, setInteractionProgress] = useState(0)
  const [interactions, setInteractions] = useState<DrugInteractionResult | null>(null)
  const [showInteractionModal, setShowInteractionModal] = useState(false)

  const [icd11Status, setIcd11Status] = useState<Status>('idle')
  const [icd11Step, setIcd11Step] = useState('Starting…')
  const [icd11Progress, setIcd11Progress] = useState(0)
  const [icd11Result, setIcd11Result] = useState<ICD11Result | null>(null)
  const [showIcd11Modal, setShowIcd11Modal] = useState(false)

  const [litStatus, setLitStatus] = useState<Status>('idle')
  const [litStep, setLitStep] = useState('Starting…')
  const [litProgress, setLitProgress] = useState(0)
  const [litResult, setLitResult] = useState<LiteratureReviewResult | null>(null)
  const [showLitModal, setShowLitModal] = useState(false)

  const [riskStatus, setRiskStatus] = useState<Status>('idle')
  const [riskStep, setRiskStep] = useState('Starting…')
  const [riskProgress, setRiskProgress] = useState(0)
  const [riskResult, setRiskResult] = useState<RiskAnalysisResult | null>(null)
  const [showRiskModal, setShowRiskModal] = useState(false)

  const [rareStatus, setRareStatus] = useState<Status>('idle')
  const [rareStep, setRareStep] = useState('Starting…')
  const [rareProgress, setRareProgress] = useState(0)
  const [rareResult, setRareResult] = useState<RareDiseaseResult | null>(null)
  const [showRareModal, setShowRareModal] = useState(false)

  const [guidelinesStatus, setGuidelinesStatus] = useState<Status>('idle')
  const [guidelinesStep, setGuidelinesStep] = useState('Starting…')
  const [guidelinesProgress, setGuidelinesProgress] = useState(0)
  const [guidelinesResult, setGuidelinesResult] = useState<GuidelinesConformanceResult | null>(null)
  const [showGuidelinesModal, setShowGuidelinesModal] = useState(false)

  const [contradictionStatus, setContradictionStatus] = useState<Status>('idle')
  const [contradictionStep, setContradictionStep] = useState('Starting…')
  const [contradictionProgress, setContradictionProgress] = useState(0)
  const [contradictionResult, setContradictionResult] = useState<ContradictionResult | null>(null)
  const [showContradictionModal, setShowContradictionModal] = useState(false)

  const [draftStatus, setDraftStatus] = useState<Status>('idle')
  const [draftStep, setDraftStep] = useState('Starting…')
  const [draftProgress, setDraftProgress] = useState(0)
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
    setAnalysisStatus('running'); setAnalysisStep('Starting…'); setAnalysisProgress(0)
    try {
      const result = await consumeSSE(
        `/api/notebooks/${notebookId}/analyze`,
        (step, pct) => { setAnalysisStep(step); setAnalysisProgress(pct) },
      )
      setAnalysis(result as ClinicalAnalysis)
      setAnalysisStatus('done')
    } catch (e: unknown) {
      alert((e as Error).message ?? 'Analysis failed')
      setAnalysisStatus('idle')
    }
  }

  async function handleRunInteractions() {
    setInteractionStatus('running'); setInteractionStep('Starting…'); setInteractionProgress(0)
    try {
      const result = await consumeSSE(
        `/api/notebooks/${notebookId}/interactions`,
        (step, pct) => { setInteractionStep(step); setInteractionProgress(pct) },
      )
      setInteractions(result as DrugInteractionResult)
      setInteractionStatus('done')
    } catch (e: unknown) {
      alert((e as Error).message ?? 'Drug interaction check failed')
      setInteractionStatus('idle')
    }
  }

  async function handleRunRisk() {
    setRiskStatus('running'); setRiskStep('Starting…'); setRiskProgress(0)
    try {
      const result = await consumeSSE(
        `/api/notebooks/${notebookId}/risk`,
        (step, pct) => { setRiskStep(step); setRiskProgress(pct) },
      )
      setRiskResult(result as RiskAnalysisResult)
      setRiskStatus('done')
    } catch (e: unknown) {
      alert((e as Error).message ?? 'Risk analysis failed')
      setRiskStatus('idle')
    }
  }

  async function handleRunLiterature() {
    setLitStatus('running'); setLitStep('Starting…'); setLitProgress(0)
    try {
      const result = await consumeSSE(
        `/api/notebooks/${notebookId}/literature`,
        (step, pct) => { setLitStep(step); setLitProgress(pct) },
      )
      setLitResult(result as LiteratureReviewResult)
      setLitStatus('done')
    } catch (e: unknown) {
      alert((e as Error).message ?? 'Literature review failed')
      setLitStatus('idle')
    }
  }

  async function handleRunContradictions() {
    setContradictionStatus('running'); setContradictionStep('Starting…'); setContradictionProgress(0)
    try {
      const result = await consumeSSE(
        `/api/notebooks/${notebookId}/contradictions`,
        (step, pct) => { setContradictionStep(step); setContradictionProgress(pct) },
      )
      setContradictionResult(result as ContradictionResult)
      setContradictionStatus('done')
    } catch (e: unknown) {
      alert((e as Error).message ?? 'Contradiction analysis failed')
      setContradictionStatus('idle')
    }
  }

  async function handleRunGuidelines() {
    setGuidelinesStatus('running'); setGuidelinesStep('Starting…'); setGuidelinesProgress(0)
    try {
      const result = await consumeSSE(
        `/api/notebooks/${notebookId}/guidelines`,
        (step, pct) => { setGuidelinesStep(step); setGuidelinesProgress(pct) },
      )
      setGuidelinesResult(result as GuidelinesConformanceResult)
      setGuidelinesStatus('done')
    } catch (e: unknown) {
      alert((e as Error).message ?? 'Guidelines analysis failed')
      setGuidelinesStatus('idle')
    }
  }

  async function handleRunRareDiseases() {
    setRareStatus('running'); setRareStep('Starting…'); setRareProgress(0)
    try {
      const result = await consumeSSE(
        `/api/notebooks/${notebookId}/rare-diseases`,
        (step, pct) => { setRareStep(step); setRareProgress(pct) },
      )
      setRareResult(result as RareDiseaseResult)
      setRareStatus('done')
    } catch (e: unknown) {
      alert((e as Error).message ?? 'Rare disease analysis failed')
      setRareStatus('idle')
    }
  }

  async function handleRunDraft() {
    setDraftStatus('running'); setDraftStep('Starting…'); setDraftProgress(0)
    try {
      const result = await consumeSSE(
        `/api/notebooks/${notebookId}/draft`,
        (step, pct) => { setDraftStep(step); setDraftProgress(pct) },
      )
      setDrafts(result as DraftResult)
      setDraftStatus('done')
    } catch (e: unknown) {
      alert((e as Error).message ?? 'Draft generation failed')
      setDraftStatus('idle')
    }
  }

  async function handleRunIcd11() {
    setIcd11Status('running'); setIcd11Step('Starting…'); setIcd11Progress(0)
    try {
      const result = await consumeSSE(
        `/api/notebooks/${notebookId}/icd11`,
        (step, pct) => { setIcd11Step(step); setIcd11Progress(pct) },
      )
      setIcd11Result(result as ICD11Result)
      setIcd11Status('done')
    } catch (e: unknown) {
      alert((e as Error).message ?? 'ICD-11 analysis failed')
      setIcd11Status('idle')
    }
  }

  return (
    <aside className={`panel-right${className ? ` ${className}` : ''}`}>
      <div className="panel-section-title">Tools</div>

      <Tool
        label="🔬 Clinical Analysis"
        status={analysisStatus}
        onRun={handleRunAnalysis}
        runningStep={analysisStep}
        runningProgress={analysisProgress}
        doneText="View clinical analysis"
        onView={() => setShowAnalysisModal(true)}
      />

      <Tool
        label="💊 Drug Interactions"
        status={interactionStatus}
        onRun={handleRunInteractions}
        runningStep={interactionStep}
        runningProgress={interactionProgress}
        doneText="View drug interactions"
        onView={() => setShowInteractionModal(true)}
      />

      <Tool
        label="🌳 ICD-11 Tree"
        status={icd11Status}
        onRun={handleRunIcd11}
        runningStep={icd11Step}
        runningProgress={icd11Progress}
        doneText="View ICD-11 tree"
        onView={() => setShowIcd11Modal(true)}
      />

      <Tool
        label="📚 Literature Review"
        status={litStatus}
        onRun={handleRunLiterature}
        runningStep={litStep}
        runningProgress={litProgress}
        doneText="View literature review"
        onView={() => setShowLitModal(true)}
      />

      <Tool
        label="⚠️ Risk Analysis"
        status={riskStatus}
        onRun={handleRunRisk}
        runningStep={riskStep}
        runningProgress={riskProgress}
        doneText="View risk analysis"
        onView={() => setShowRiskModal(true)}
      />

      <Tool
        label="⚡ Contradiction Detector"
        status={contradictionStatus}
        onRun={handleRunContradictions}
        runningStep={contradictionStep}
        runningProgress={contradictionProgress}
        doneText="View contradictions"
        onView={() => setShowContradictionModal(true)}
      />

      <Tool
        label="📋 Guidelines Conformance"
        status={guidelinesStatus}
        onRun={handleRunGuidelines}
        runningStep={guidelinesStep}
        runningProgress={guidelinesProgress}
        doneText="View guidelines conformance"
        onView={() => setShowGuidelinesModal(true)}
      />

      <Tool
        label="🧬 Rare Disease Finder"
        status={rareStatus}
        onRun={handleRunRareDiseases}
        runningStep={rareStep}
        runningProgress={rareProgress}
        doneText="View rare disease matches"
        onView={() => setShowRareModal(true)}
      />

      <Tool
        label="📝 Draft Document"
        status={draftStatus}
        onRun={handleRunDraft}
        runningStep={draftStep}
        runningProgress={draftProgress}
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
  runningStep: string
  runningProgress: number
  doneText: string
  onView: () => void
}

function Tool({ label, status, onRun, runningStep, runningProgress, doneText, onView }: ToolProps) {
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
            <ProgressDisplay step={runningStep} target={runningProgress} />
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

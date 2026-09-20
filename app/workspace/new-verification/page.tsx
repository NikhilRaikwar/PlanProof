'use client'

import React, { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import {
  Activity,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Copy,
  Database,
  FileText,
  Info,
  Loader2,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  Upload,
  Zap,
} from 'lucide-react'
import { GithubIcon } from '@/components/repo-context-chip'

export default function NewVerificationPage() {
  const router = useRouter()
  const [isRunning, setIsRunning] = useState(false)
  const [runStageIndex, setRunStageIndex] = useState(0)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  // Form State
  const [changeRequestText, setChangeRequestText] = useState('Add partial refund capability while preserving current full-refund behavior.')
  const [candidatePlanText, setCandidatePlanText] = useState(`1. Add an optional amount parameter to PaymentService.refund().
2. Forward the amount to the provider layer.
3. Preserve the current full-refund path when no amount is supplied.
4. Reuse existing idempotency handling.
5. Review billing and schema assumptions during verification.`)
  const [showSettingsAccordion, setShowSettingsAccordion] = useState(false)

  const runStages = [
    { title: 'Resolving immutable repository snapshot (8f3c1a2)', tool: 'git_snapshot' },
    { title: 'Extracting candidate proof obligations & claims', tool: 'llm_assumption_parser' },
    { title: 'Grounding symbols & AST dependency call-graphs', tool: 'symbol_indexer' },
    { title: 'Checking persistence constraints & entity schemas', tool: 'schema_validator' },
    { title: 'Inspecting OpenAPI response contracts & clients', tool: 'openapi_diff' },
    { title: 'Synthesizing evidence & generating verification report', tool: 'gate_synthesizer' }
  ]

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadFileName, setUploadFileName] = useState<string | null>(null)

  const handlePastePlan = async () => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.readText) {
        const text = await navigator.clipboard.readText()
        if (text && text.trim().length > 0) {
          setCandidatePlanText(text)
          setUploadFileName(null)
          return
        }
      }
    } catch (err) {
      // Fallback to sample plan
    }
    setCandidatePlanText(`1. Add an optional amount parameter to PaymentService.refund().\n2. Forward the amount to the provider layer.\n3. Preserve the current full-refund path when no amount is supplied.\n4. Reuse existing idempotency handling.\n5. Review billing and schema assumptions during verification.`)
    setUploadFileName(null)
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploadFileName(file.name)
    const reader = new FileReader()
    reader.onload = (event) => {
      const content = event.target?.result as string
      if (content) {
        setCandidatePlanText(content)
      }
    }
    reader.readAsText(file)
  }

  // Handle start verification
  const handleStartVerification = () => {
    setIsRunning(true)
    setRunStageIndex(0)
    setElapsedSeconds(0)

    let current = 0
    const interval = setInterval(() => {
      current += 1
      setRunStageIndex(current)
      if (current >= runStages.length - 1) {
        clearInterval(interval)
        setTimeout(() => {
          router.push('/workspace/runs/run-101')
        }, 1200)
      }
    }, 900)
  }

  // Timer tick for live run
  useEffect(() => {
    let timer: any
    if (isRunning) {
      timer = setInterval(() => setElapsedSeconds(s => s + 1), 1000)
    }
    return () => clearInterval(timer)
  }, [isRunning])

  if (isRunning) {
    return (
      <div className="dashboard-two-col-grid">
        <div className="card-panel-white">
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 800, color: '#EA580C', textTransform: 'uppercase', letterSpacing: '0.8px', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <Activity size={13} />
                <span>LIVE VERIFICATION RUN IN PROGRESS</span>
              </div>
              <h2 style={{ fontSize: 20, fontWeight: 850, color: '#0F172A', margin: 0 }}>Investigating Proof Obligations</h2>
              <p style={{ fontSize: 12, color: '#64748B', marginTop: 4, margin: '4px 0 0' }}>
                Gathering evidence from <code>nikhilraikwar / planproof</code> at commit <code>8f3c1a2</code>.
              </p>
            </div>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: '#FFF7ED', border: '1px solid #FFD9CA', color: '#EA580C', fontSize: 11, fontWeight: 800, padding: '4px 10px', borderRadius: 9999 }}>
              <Loader2 size={13} className="animate-spin" />
              STAGE {runStageIndex + 1}/{runStages.length}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {runStages.map((stage, idx) => {
              const isComplete = idx < runStageIndex
              const isActive = idx === runStageIndex
              const isPending = idx > runStageIndex

              return (
                <div 
                  key={stage.title}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: isComplete ? '1px solid #A7F3D0' : isActive ? '1px solid #FDBA74' : '1px solid #E2E8F0',
                    background: isComplete ? '#ECFDF5' : isActive ? '#FFF7ED' : '#F8FAFC',
                    color: isComplete ? '#065F46' : isActive ? '#9A3412' : '#94A3B8',
                    fontSize: 12,
                    fontWeight: 650
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    {isComplete && <CheckCircle2 size={16} style={{ color: '#059669' }} />}
                    {isActive && <Loader2 size={16} style={{ color: '#EA580C' }} className="animate-spin" />}
                    {isPending && <Circle size={16} style={{ color: '#CBD5E1' }} />}
                    <span>{stage.title}</span>
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, background: '#FFFFFF', border: '1px solid #E2E8F0', padding: '2px 8px', borderRadius: 4, color: '#475569' }}>
                    {stage.tool}
                  </span>
                </div>
              )
            })}
          </div>

          <div style={{ marginTop: 20, padding: 14, background: '#0F172A', color: '#F8FAFC', borderRadius: 8, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            <div style={{ fontSize: 10, color: '#94A3B8', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Terminal size={12} /> Live Action Stream
            </div>
            <p style={{ color: '#34D399', margin: '3px 0' }}>➜ [symbol_index] Found 142 AST nodes in services/payment.py.</p>
            <p style={{ color: '#7DD3FC', margin: '3px 0' }}>➜ [schema_probe] Inspecting UNIQUE constraint on refunds.payment_id.</p>
            <p style={{ color: '#FCD34D', margin: '3px 0' }}>➜ [counter_evidence] Conflict detected: PaymentService.refund() ignores amount param.</p>
          </div>
        </div>

        <div className="card-panel-white" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <h3 className="card-heading-compact" style={{ margin: 0 }}>Run Telemetry & Budget</h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9', color: '#475569' }}>
              <span>Elapsed Time</span>
              <strong style={{ color: '#0F172A', fontFamily: 'var(--font-mono)' }}>00:{elapsedSeconds < 10 ? `0${elapsedSeconds}` : elapsedSeconds}s</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9', color: '#475569' }}>
              <span>Model Invocations</span>
              <strong style={{ color: '#0F172A', fontFamily: 'var(--font-mono)' }}>07 calls</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9', color: '#475569' }}>
              <span>Tool Calls</span>
              <strong style={{ color: '#0F172A', fontFamily: 'var(--font-mono)' }}>24 tools</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9', color: '#475569' }}>
              <span>Cost Estimate</span>
              <strong style={{ color: '#0F172A', fontFamily: 'var(--font-mono)' }}>$0.24</strong>
            </div>
          </div>

          <button 
            onClick={() => router.push('/workspace/runs/run-101')}
            style={{ width: '100%', background: '#0F172A', color: '#FFFFFF', fontSize: 12, fontWeight: 750, padding: '10px 0', borderRadius: 8, border: 'none', cursor: 'pointer', marginTop: 10 }}
          >
            Skip to Report
          </button>
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Page Title & Status Pill */}
      <div className="page-header-block">
        <div className="preflight-eyebrow">
          <Sparkles size={13} />
          <span>PRE-FLIGHT VERIFICATION</span>
        </div>
        <h1 className="page-main-title">
          Verify an engineering plan
        </h1>
        <p className="page-main-desc">
          Check a proposed implementation against the connected codebase before a coding agent starts building.
        </p>
        <div className="connected-pill-badge">
          <Check size={13} strokeWidth={3} />
          <span>Repository connected and indexed.</span>
        </div>
      </div>

      {/* Two Column Layout */}
      <div className="dashboard-two-col-grid">
        {/* Left Column: Verification Inputs Card */}
        <div className="card-panel-white">
          <h2 className="card-panel-title">Verification inputs</h2>
          <p className="card-panel-sub">Connect repository context, describe the change, and provide a candidate plan.</p>

          <div>
            {/* Target Repository */}
            <div className="form-field-block">
              <div className="form-field-header">
                <label className="form-field-label">Target repository</label>
                <span className="ast-fresh-pill">
                  <span className="synced-green-dot" />
                  AST index fresh
                </span>
              </div>
              <div className="custom-select-box">
                <div className="select-box-left">
                  <GithubIcon size={15} />
                  <span>nikhilraikwar / planproof</span>
                </div>
                <ChevronDown size={14} style={{ color: '#94A3B8' }} />
              </div>
              <div className="field-sub-meta">
                <span>Snapshot commit:</span>
                <span className="commit-mini-tag">8f3c1a2</span>
                <span>• Branch: main</span>
              </div>
            </div>

            {/* What are you planning to change? */}
            <div className="form-field-block">
              <label className="form-field-label">
                What are you planning to change?
              </label>
              <input 
                type="text"
                value={changeRequestText}
                onChange={(e) => setChangeRequestText(e.target.value)}
                className="custom-text-input"
                placeholder="Describe the engineering change..."
              />
              <div className="char-counter">
                {changeRequestText.length}/500
              </div>
            </div>

            {/* Candidate Plan */}
            <div className="form-field-block">
              <div className="form-field-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <label className="form-field-label" style={{ margin: 0 }}>Candidate plan</label>
                  {uploadFileName && (
                    <span style={{ fontSize: 10, fontWeight: 700, color: '#059669', background: '#ECFDF5', padding: '1px 6px', borderRadius: 4 }}>
                      📄 {uploadFileName}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button 
                    type="button"
                    onClick={handlePastePlan}
                    className="btn-plan-action"
                    title="Paste plan from clipboard"
                  >
                    <Copy size={11} />
                    <span>Paste plan</span>
                  </button>

                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileUpload}
                    accept=".md,.txt,.json,.yaml,.yml"
                    style={{ display: 'none' }}
                  />

                  <button 
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="btn-plan-action"
                    title="Upload markdown/text/JSON plan document"
                  >
                    <Upload size={11} />
                    <span>Upload plan</span>
                  </button>
                </div>
              </div>
              <textarea 
                rows={7}
                value={candidatePlanText}
                onChange={(e) => setCandidatePlanText(e.target.value)}
                className="custom-textarea"
                placeholder="1. Enter proposed changes or steps...&#10;2. Paste engineering plan from Claude Code, Codex, or PM doc...&#10;3. Click upload plan to import a document..."
              />
              <div className="char-counter">
                {candidatePlanText.length}/5,000
              </div>
              <div className="field-info-caption">
                <Info size={13} style={{ color: '#94A3B8' }} />
                <span>PlanProof will automatically extract claims and turn them into testable proof obligations.</span>
              </div>
            </div>

            {/* Verification Settings Accordion (Pure Defaults) */}
            <div>
              <div 
                onClick={() => setShowSettingsAccordion(!showSettingsAccordion)}
                className="settings-accordion-row"
              >
                <div className="accordion-left-title">
                  <ChevronRight size={14} style={{ transform: showSettingsAccordion ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s ease' }} />
                  <span>Verification settings</span>
                </div>
                <span className="accordion-right-sub">3 defaults</span>
              </div>

              {showSettingsAccordion && (
                <div style={{ marginTop: 10, padding: 12, background: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, fontSize: 12 }}>
                  <div>
                    <span style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8', textTransform: 'uppercase', display: 'block' }}>Engine Pipeline</span>
                    <strong style={{ color: '#1E293B', fontSize: 12 }}>Deterministic AST + LLM</strong>
                  </div>
                  <div>
                    <span style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8', textTransform: 'uppercase', display: 'block' }}>Verification Depth</span>
                    <strong style={{ color: '#1E293B', fontSize: 12 }}>Standard (12 claims)</strong>
                  </div>
                  <div>
                    <span style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8', textTransform: 'uppercase', display: 'block' }}>Probe Permission</span>
                    <strong style={{ color: '#1E293B', fontSize: 12 }}>Read-only AST & Grep</strong>
                  </div>
                </div>
              )}
            </div>

            {/* Bottom Action Row */}
            <div className="verification-action-bar">
              <div className="run-cost-estimate">
                <Zap size={13} style={{ color: '#94A3B8' }} />
                <span>Estimated run <strong>~30–40 sec</strong> • up to <strong>$0.42</strong></span>
              </div>

              <button 
                onClick={handleStartVerification}
                className="btn-verify-plan-cta"
              >
                <span>Verify this plan</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Stacked Cards */}
        <div className="right-stack-col">
          {/* Card 1: What happens next */}
          <div className="what-next-card">
            <h3 className="card-heading-compact">What happens next</h3>

            <div className="next-steps-list">
              {/* Step 1 */}
              <div className="next-step-item">
                <div className="step-icon-square">
                  <FileText size={16} />
                </div>
                <div className="step-content-box">
                  <strong className="step-content-title">1. Extract claims</strong>
                  <p className="step-content-desc">
                    Turn plan statements into testable obligations.
                  </p>
                </div>
              </div>

              {/* Vertical connector */}
              <div className="step-vertical-connector" />

              {/* Step 2 */}
              <div className="next-step-item">
                <div className="step-icon-square">
                  <Search size={16} />
                </div>
                <div className="step-content-box">
                  <strong className="step-content-title">2. Gather evidence</strong>
                  <p className="step-content-desc">
                    Search code, schemas, dependencies, and tests.
                  </p>
                </div>
              </div>

              {/* Vertical connector */}
              <div className="step-vertical-connector" />

              {/* Step 3 */}
              <div className="next-step-item">
                <div className="step-icon-square">
                  <ShieldCheck size={16} />
                </div>
                <div className="step-content-box">
                  <strong className="step-content-title">3. Gate the plan</strong>
                  <p className="step-content-desc">
                    Verify, disprove, or pause for a human decision.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Card 2: Repository readiness */}
          <div className="readiness-card">
            <h3 className="card-heading-compact">Repository readiness</h3>

            <div className="readiness-rows">
              <div className="readiness-row-item">
                <div className="readiness-row-left">
                  <Check size={14} style={{ color: '#10B981', strokeWidth: 3 }} />
                  <span>Snapshot pinned</span>
                </div>
                <span className="readiness-value-badge">
                  8f3c1a2
                </span>
              </div>

              <div className="readiness-row-item">
                <div className="readiness-row-left">
                  <Check size={14} style={{ color: '#10B981', strokeWidth: 3 }} />
                  <span>Symbol index</span>
                </div>
                <span className="readiness-value-fresh">Fresh</span>
              </div>

              <div className="readiness-row-item">
                <div className="readiness-row-left">
                  <Check size={14} style={{ color: '#10B981', strokeWidth: 3 }} />
                  <span>Dependency graph</span>
                </div>
                <span className="readiness-value-fresh">Ready</span>
              </div>

              <div className="readiness-row-item">
                <div className="readiness-row-left">
                  <Check size={14} style={{ color: '#10B981', strokeWidth: 3 }} />
                  <span>Schema index</span>
                </div>
                <span className="readiness-value-fresh">Ready</span>
              </div>
            </div>

            <div className="readiness-footer-note">
              <Database size={13} style={{ color: '#94A3B8' }} />
              <span>Your repository is indexed and ready for verification.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

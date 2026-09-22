'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { 
  AlertCircle, 
  ArrowLeft, 
  Check, 
  CheckCircle2, 
  Clock, 
  Code2, 
  Copy,
  FileText, 
  FolderGit2, 
  GitBranch, 
  GitCommit, 
  Layers3, 
  ShieldAlert, 
  ShieldCheck, 
  Sparkles,
  Terminal, 
  Wrench, 
  XCircle 
} from 'lucide-react'
import { api, ApiError, Evidence, Obligation, RevisedPlan, RunProjection } from '@/lib/api'
import { useWorkspace } from '@/components/workspace-context'

const terminalStatuses = new Set(['COMPLETE', 'BLOCKED', 'INCONCLUSIVE', 'FAILED'])
const eventTypes = [
  'run_created', 
  'obligations_extracted', 
  'obligation_started', 
  'tool_started', 
  'tool_completed', 
  'tool_failed', 
  'evidence_added', 
  'human_question_created', 
  'human_answered', 
  'obligation_completed', 
  'run_completed', 
  'run_failed'
]

export default function RunReportPage() {
  const { runId } = useParams<{ runId: string }>()
  const { setRunContext } = useWorkspace()

  const [projection, setProjection] = useState<RunProjection | null>(null)
  const [obligations, setObligations] = useState<Obligation[]>([])
  const [evidence, setEvidence] = useState<Evidence[]>([])
  const [revisedPlan, setRevisedPlan] = useState<RevisedPlan | null>(null)
  const [copiedPlan, setCopiedPlan] = useState(false)
  const [events, setEvents] = useState<string[]>([])
  const [streamState, setStreamState] = useState<'connecting' | 'live' | 'reconnecting'>('connecting')
  const [answerMap, setAnswerMap] = useState<Record<string, string>>({})
  const [submittingQuestionId, setSubmittingQuestionId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const loadTimer = useRef<number | null>(null)

  const load = async () => {
    try {
      const [p, o, e, r] = await Promise.all([
        api.run(runId), 
        api.obligations(runId), 
        api.evidence(runId),
        api.revisedPlan(runId).catch(() => null)
      ])
      setProjection(p)
      setObligations(o)
      setEvidence(e)
      setRevisedPlan(r)
      setError('')
    } catch (x) {
      if (!projection) {
        setError(x instanceof ApiError ? x.message : 'Could not load run report.')
      }
    }
  }

  const triggerLoad = () => {
    if (loadTimer.current) return
    loadTimer.current = window.setTimeout(() => {
      loadTimer.current = null
      void load()
    }, 400)
  }

  useEffect(() => { 
    void load() 
  }, [runId])

  // Set temporary run context on mount, clean up on unmount
  useEffect(() => {
    if (projection?.repository && projection?.snapshot) {
      setRunContext({
        repositoryId: projection.repository.id,
        repositoryFullName: projection.repository.full_name || projection.repository.name,
        ref: projection.snapshot.requested_ref || 'main',
        snapshotId: projection.snapshot.id,
        commitSha: projection.snapshot.resolved_commit_sha || undefined,
        snapshotStatus: projection.snapshot.status,
        isRunContext: true,
      })
    }
    return () => {
      setRunContext(null)
    }
  }, [projection, setRunContext])

  useEffect(() => {
    if (!projection || terminalStatuses.has(projection.run.status)) return
    const timer = window.setTimeout(() => { void load() }, 3_000)
    return () => window.clearTimeout(timer)
  }, [projection, runId])

  useEffect(() => {
    if (!projection || terminalStatuses.has(projection.run.status)) return
    const source = new EventSource(api.eventsUrl(runId))
    source.onopen = () => setStreamState('live')
    const receive = (event: MessageEvent) => {
      setEvents(old => old.some(item => item.startsWith(`${event.lastEventId}:`)) ? old : [...old, `${event.lastEventId}:${event.data}`])
      triggerLoad()
    }
    eventTypes.forEach(type => source.addEventListener(type, receive))
    source.onerror = () => setStreamState('reconnecting')
    return () => source.close()
  }, [projection, runId])

  const submitAnswer = async (questionId: string) => { 
    const ans = answerMap[questionId]
    if (!ans || !ans.trim()) return
    setSubmittingQuestionId(questionId)
    try { 
      await api.answer(questionId, ans.trim())
      setAnswerMap(prev => ({ ...prev, [questionId]: '' }))
      void load() 
    } catch (e) { 
      setError(e instanceof ApiError ? e.message : 'Could not submit authorized decision.') 
    } finally {
      setSubmittingQuestionId(null)
    }
  }

  if (error && !projection) return <div className="card-panel-white" style={{ color: '#B91C1C' }}>{error}</div>
  if (!projection) return <div className="card-panel-white">Loading run report…</div>

  const { run, repository, snapshot, plan } = projection

  const isBlocked = run.status === 'BLOCKED'
  const isComplete = run.status === 'COMPLETE'
  const isHumanWait = run.status === 'HUMAN_WAIT' || run.status === 'HUMAN_DECISION_REQUIRED'

  const repoName = repository?.full_name || repository?.name || 'Repository'
  const commit = snapshot?.resolved_commit_sha ? snapshot.resolved_commit_sha.slice(0, 7) : undefined
  const ref = snapshot?.requested_ref || 'main'
  const changeDesc = plan?.change_request || 'Verification run change request'

  // Counters derive directly from run-scoped collections
  const verifiedCount = projection.obligation_counts['VERIFIED'] ?? 0
  const disprovedCount = projection.obligation_counts['DISPROVED'] ?? 0
  const inconclusiveCount = projection.obligation_counts['INCONCLUSIVE'] ?? 0
  const humanRequiredCount = projection.obligation_counts['HUMAN_REQUIRED'] ?? 0
  const totalObligations = obligations.length

  const openQuestions = projection.human_questions.filter(q => q.status === 'OPEN')
  const answeredQuestions = projection.human_questions.filter(q => q.status === 'ANSWERED')

  const handleCopyUpdatedPlan = async () => {
    if (!revisedPlan || !revisedPlan.implementation_plan) return
    const text = `# Updated Implementation Plan (v${revisedPlan.revision_version})\n\n` +
      `**Status**: ${revisedPlan.status}\n\n` +
      `## Executive Summary\n${revisedPlan.executive_summary || 'Plan updated based on immutable repository evidence.'}\n\n` +
      `## Ordered Implementation Steps\n\n` +
      revisedPlan.implementation_plan.map(s => (
        `### Step ${s.order}: ${s.action}\n` +
        (s.existing_target_files?.length ? `**Target Existing Files**:\n${s.existing_target_files.map(f => `- \`${f}\``).join('\n')}\n\n` : '') +
        (s.proposed_new_files?.length ? `**Proposed New Files**:\n${s.proposed_new_files.map(f => `- \`${f}\` (new)`).join('\n')}\n\n` : '') +
        (s.target_symbols?.length ? `**Target Symbols**:\n${s.target_symbols.map(sym => `- \`${sym}\``).join('\n')}\n\n` : '') +
        `**Rationale**:\n${s.rationale}\n\n` +
        (s.basis_fact_ids?.length ? `*Basis Facts*: ${s.basis_fact_ids.join(', ')}\n` : '')
      )).join('\n\n')

    try {
      await navigator.clipboard.writeText(text)
      setCopiedPlan(true)
      setTimeout(() => setCopiedPlan(false), 2000)
    } catch {
      // ignore clipboard error
    }
  }

  return (
    <div style={{ display: 'grid', gap: 20 }}>
      {/* Top Navigation & Run Context Notice */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <Link 
          href="/workspace/runs" 
          style={{ 
            display: 'inline-flex', 
            alignItems: 'center', 
            gap: 6, 
            fontSize: 12.5, 
            color: '#64748B', 
            textDecoration: 'none', 
            fontWeight: 600 
          }}
        >
          <ArrowLeft size={14} /> Back to verification runs
        </Link>

        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, background: '#EFF6FF', color: '#1E40AF', padding: '4px 10px', borderRadius: 6, border: '1px solid #DBEAFE' }}>
          <FolderGit2 size={13} />
          <span>Run-authoritative context: <strong>{repoName}</strong> · snapshot {run.snapshot_id.slice(0, 7)}</span>
        </div>
      </div>

      {/* Report Header */}
      <div className="card-panel-white" style={{ padding: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
          <div style={{ display: 'grid', gap: 8 }}>
            <div className="preflight-eyebrow" style={{ margin: 0 }}>
              <Layers3 size={13} />
              <span>PRE-FLIGHT GATE REPORT · RUN {run.id.slice(0, 8)}</span>
            </div>
            
            <h1 className="page-main-title" style={{ fontSize: 24, margin: 0 }}>
              Gate: {run.status.replaceAll('_', ' ')}
            </h1>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12.5, color: '#64748B', flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 700, color: '#0F172A' }}>{repoName}</span>
              <span>·</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <GitBranch size={13} /> {ref}
              </span>
              {commit && (
                <span className="commit-mini-tag">
                  <GitCommit size={11} style={{ marginRight: 2 }} />
                  {commit}
                </span>
              )}
              <span>·</span>
              <span>Plan version {plan?.version ?? 1}</span>
              <span>·</span>
              <span>{new Date(run.created_at).toLocaleString()}</span>
            </div>
          </div>

          <div style={{ textAlign: 'right' }}>
            {isBlocked && (
              <span className="badge-pill-base badge-blocked" style={{ fontSize: 13, padding: '6px 14px' }}>
                <ShieldAlert size={16} /> GATE BLOCKED
              </span>
            )}
            {isComplete && (
              <span className="badge-pill-base badge-verified" style={{ fontSize: 13, padding: '6px 14px' }}>
                <ShieldCheck size={16} /> GATE PASSED
              </span>
            )}
            {isHumanWait && (
              <span className="badge-pill-base badge-human" style={{ fontSize: 13, padding: '6px 14px' }}>
                <Clock size={16} /> HUMAN DECISION REQUIRED
              </span>
            )}
            {!isBlocked && !isComplete && !isHumanWait && (
              <span className="badge-pill-base badge-inconclusive" style={{ fontSize: 13, padding: '6px 14px' }}>
                {run.status === 'INCONCLUSIVE' ? 'INCONCLUSIVE' : run.status}
              </span>
            )}
          </div>
        </div>

        {/* Change Request Summary */}
        <div style={{ marginTop: 18, paddingTop: 16, borderTop: '1px solid #F1F5F9', display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#64748B', letterSpacing: 0.5 }}>
            Change Request Under Verification
          </span>
          <p style={{ fontSize: 14, color: '#0F172A', margin: 0, fontWeight: 550, lineHeight: 1.4 }}>
            {changeDesc}
          </p>
        </div>
      </div>

      {/* Summary Metrics Grid */}
      <div className="run-metrics-grid">
        <div className="card-panel-white" style={{ padding: 14, textAlign: 'center' }}>
          <span style={{ fontSize: 11, color: '#64748B', fontWeight: 650 }}>Proof Obligations</span>
          <strong style={{ fontSize: 20, color: '#0F172A', display: 'block', marginTop: 4 }}>{totalObligations}</strong>
        </div>
        <div className="card-panel-white" style={{ padding: 14, textAlign: 'center' }}>
          <span style={{ fontSize: 11, color: '#16A34A', fontWeight: 650 }}>Verified</span>
          <strong style={{ fontSize: 20, color: '#16A34A', display: 'block', marginTop: 4 }}>{verifiedCount}</strong>
        </div>
        <div className="card-panel-white" style={{ padding: 14, textAlign: 'center' }}>
          <span style={{ fontSize: 11, color: '#DC2626', fontWeight: 650 }}>Disproved</span>
          <strong style={{ fontSize: 20, color: '#DC2626', display: 'block', marginTop: 4 }}>{disprovedCount}</strong>
        </div>
        <div className="card-panel-white" style={{ padding: 14, textAlign: 'center' }}>
          <span style={{ fontSize: 11, color: '#D97706', fontWeight: 650 }}>Inconclusive</span>
          <strong style={{ fontSize: 20, color: '#D97706', display: 'block', marginTop: 4 }}>{inconclusiveCount}</strong>
        </div>
        <div className="card-panel-white" style={{ padding: 14, textAlign: 'center' }}>
          <span style={{ fontSize: 11, color: '#B45309', fontWeight: 650 }}>Human Decisions</span>
          <strong style={{ fontSize: 20, color: '#B45309', display: 'block', marginTop: 4 }}>{projection.human_questions.length}</strong>
        </div>
        <div className="card-panel-white" style={{ padding: 14, textAlign: 'center' }}>
          <span style={{ fontSize: 11, color: '#64748B', fontWeight: 650 }}>Evidence Items</span>
          <strong style={{ fontSize: 20, color: '#0F172A', display: 'block', marginTop: 4 }}>{projection.evidence_count}</strong>
        </div>
        <div className="card-panel-white" style={{ padding: 14, textAlign: 'center' }}>
          <span style={{ fontSize: 11, color: '#64748B', fontWeight: 650 }}>Tool Executions</span>
          <strong style={{ fontSize: 20, color: '#0F172A', display: 'block', marginTop: 4 }}>{projection.tool_execution_count ?? run.tool_call_count}</strong>
        </div>
        <div className="card-panel-white" style={{ padding: 14, textAlign: 'center' }}>
          <span style={{ fontSize: 11, color: '#64748B', fontWeight: 650 }}>Model Calls</span>
          <strong style={{ fontSize: 20, color: '#0F172A', display: 'block', marginTop: 4 }}>{run.model_call_count}</strong>
        </div>
      </div>

      {/* Active Human Decision Banner (if open questions exist and run is waiting) */}
      {isHumanWait && openQuestions.length > 0 && (
        <div className="card-panel-white" style={{ border: '2px solid #F59E0B', background: '#FFFBEB', padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <AlertCircle size={18} color="#D97706" />
            <strong style={{ fontSize: 15, color: '#92400E' }}>Authorized Human Decision Required</strong>
          </div>

          <div style={{ display: 'grid', gap: 16 }}>
            {openQuestions.map(q => (
              <div key={q.id} style={{ background: '#FFFFFF', padding: 16, borderRadius: 8, border: '1px solid #FDE68A', display: 'grid', gap: 10 }}>
                <div>
                  <strong style={{ fontSize: 14, color: '#0F172A' }}>{q.question}</strong>
                  <p style={{ fontSize: 12, color: '#64748B', margin: '4px 0 0' }}>
                    {q.why_needed} — <span style={{ color: '#B45309', fontWeight: 600 }}>Authority required: {q.authority_required}</span>
                  </p>
                </div>

                <textarea
                  className="custom-textarea"
                  value={answerMap[q.id] || ''}
                  onChange={e => setAnswerMap(prev => ({ ...prev, [q.id]: e.target.value }))}
                  placeholder="Record the authorized technical or business decision (e.g. Approved mobile contract compatibility on ticket SEC-102)…"
                  rows={3}
                />

                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    className="btn-verify-plan-cta"
                    disabled={submittingQuestionId === q.id || !answerMap[q.id]?.trim()}
                    onClick={() => void submitAnswer(q.id)}
                  >
                    {submittingQuestionId === q.id ? 'Submitting…' : 'Submit decision'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workflow Event Timeline */}
      {events.length > 0 && (
        <div className="card-panel-white">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ fontSize: 13, color: '#0F172A' }}>Workflow Event Telemetry</strong>
            <span style={{ fontSize: 11, color: '#64748B' }}>
              {terminalStatuses.has(run.status)
                ? 'Workflow finalized'
                : streamState === 'live'
                ? 'Connected to live stream'
                : 'Reconnecting…'}
            </span>
          </div>
          <div style={{ maxHeight: 160, overflowY: 'auto', background: '#F8FAFC', padding: 10, borderRadius: 6, fontSize: 12, display: 'grid', gap: 6 }}>
            {events.map((event, idx) => {
              // Parse clean summary if formatted as sequence:JSON or raw text
              let displayEvent = event
              try {
                const colonIdx = event.indexOf(':')
                if (colonIdx !== -1) {
                  const payload = event.slice(colonIdx + 1)
                  const parsed = JSON.parse(payload)
                  if (parsed.summary) {
                    displayEvent = parsed.summary
                  } else if (parsed.event_type) {
                    displayEvent = `${parsed.event_type}: ${parsed.summary || ''}`
                  }
                }
              } catch {
                // Keep clean raw string
              }
              return (
                <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#334155' }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#EA580C', flexShrink: 0 }} />
                  <span>{displayEvent}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Proof Obligations with Attached Evidence */}
      <div className="card-panel-white">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 750, color: '#0F172A', margin: 0 }}>
              Proof Obligations ({obligations.length})
            </h2>
            <span style={{ fontSize: 12, color: '#64748B' }}>
              Formal verification claims extracted from candidate engineering plan
            </span>
          </div>
        </div>

        {obligations.length === 0 ? (
          <p style={{ color: '#64748B', fontSize: 13 }}>No proof obligations have been extracted for this plan yet.</p>
        ) : (
          <div style={{ display: 'grid', gap: 16 }}>
            {obligations.map(obligation => {
              // Find supporting and counter evidence for this obligation
              const supporting = evidence.filter(ev => 
                (obligation.evidence_ids || []).includes(ev.id) || 
                (ev.obligation_id === obligation.id && ev.relationship === 'SUPPORTS')
              )
              const counter = evidence.filter(ev => 
                (obligation.counter_evidence_ids || []).includes(ev.id) || 
                (ev.obligation_id === obligation.id && ev.relationship === 'CONTRADICTS')
              )
              const linkedEvidence = [...supporting, ...counter]

              // Find human questions associated with this obligation
              const obAnswered = answeredQuestions.filter(q => q.obligation_id === obligation.id)
              const obOpen = openQuestions.filter(q => q.obligation_id === obligation.id)

              const isObVerified = obligation.status === 'VERIFIED'
              const isObDisproved = obligation.status === 'DISPROVED'
              const isObInconclusive = obligation.status === 'INCONCLUSIVE'
              const isObHumanRequired = obligation.status === 'HUMAN_REQUIRED' || obOpen.length > 0
              const inconclusiveReason = obligation.proposal_metadata?.inconclusive_reason || 'No supporting repository evidence found within investigation budget'

              return (
                <div 
                  key={obligation.id} 
                  style={{ 
                    border: '1px solid #E2E8F0', 
                    borderRadius: 8, 
                    padding: 16, 
                    background: isObDisproved ? '#FFF5F5' : isObInconclusive ? '#FAFAFA' : '#FFFFFF' 
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
                    <div style={{ display: 'grid', gap: 4, flex: 1, minWidth: 260 }}>
                      <strong style={{ fontSize: 14, color: '#0F172A', lineHeight: 1.4 }}>
                        {obligation.statement}
                      </strong>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: '#64748B' }}>
                        <span>Category: <strong>{obligation.category}</strong></span>
                        <span>·</span>
                        <span>Criticality: <strong>{obligation.criticality}</strong></span>
                        <span>·</span>
                        <span>Evidence items: <strong>{linkedEvidence.length}</strong></span>
                      </div>
                      {isObInconclusive && (
                        <p style={{ fontSize: 12, color: '#64748B', margin: '4px 0 0', fontStyle: 'italic' }}>
                          Reason: {inconclusiveReason}
                        </p>
                      )}
                    </div>

                    <div>
                      {isObVerified ? (
                        <span className="badge-pill-base badge-verified">
                          <CheckCircle2 size={12} /> VERIFIED
                        </span>
                      ) : isObDisproved ? (
                        <span className="badge-pill-base badge-blocked">
                          <XCircle size={12} /> DISPROVED
                        </span>
                      ) : isObHumanRequired ? (
                        <span className="badge-pill-base badge-human">
                          <Clock size={12} /> HUMAN DECISION REQUIRED
                        </span>
                      ) : isObInconclusive ? (
                        <span className="badge-pill-base badge-inconclusive">
                          INCONCLUSIVE
                        </span>
                      ) : (
                        <span className="badge-pill-base badge-queued">
                          {obligation.status}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Persisted Human Decision History (if resolved) */}
                  {obAnswered.length > 0 && (
                    <div style={{ marginTop: 12, padding: 12, borderRadius: 6, background: '#F0FDF4', border: '1px solid #BBF7D0', display: 'grid', gap: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <Check size={14} color="#16A34A" />
                        <strong style={{ fontSize: 12, color: '#166534' }}>
                          Resolved by authorized human decision
                        </strong>
                        {obAnswered[0].answered_at && (
                          <span style={{ fontSize: 11, color: '#15803D' }}>
                            · {new Date(obAnswered[0].answered_at).toLocaleString()}
                          </span>
                        )}
                      </div>
                      <p style={{ fontSize: 12.5, color: '#14532D', margin: 0, fontWeight: 600 }}>
                        Decision: {obAnswered[0].answer}
                      </p>
                      <span style={{ fontSize: 11, color: '#166534' }}>
                        Question: {obAnswered[0].question} — {obAnswered[0].why_needed}
                      </span>
                    </div>
                  )}

                  {/* Open Human Decision Required for this obligation */}
                  {isHumanWait && obOpen.length > 0 && (
                    <div style={{ marginTop: 12, padding: 12, borderRadius: 6, background: '#FFFBEB', border: '1px solid #FDE68A', display: 'grid', gap: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <AlertCircle size={14} color="#D97706" />
                        <strong style={{ fontSize: 12, color: '#92400E' }}>
                          Human authority required for this claim
                        </strong>
                      </div>
                      <p style={{ fontSize: 12.5, color: '#0F172A', margin: 0 }}>
                        {obOpen[0].question}
                      </p>
                      <textarea
                        className="custom-textarea"
                        value={answerMap[obOpen[0].id] || ''}
                        onChange={e => setAnswerMap(prev => ({ ...prev, [obOpen[0].id]: e.target.value }))}
                        placeholder="Record the authorized decision…"
                        rows={2}
                      />
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          className="btn-verify-plan-cta"
                          style={{ fontSize: 11, padding: '4px 10px' }}
                          disabled={submittingQuestionId === obOpen[0].id || !answerMap[obOpen[0].id]?.trim()}
                          onClick={() => void submitAnswer(obOpen[0].id)}
                        >
                          {submittingQuestionId === obOpen[0].id ? 'Submitting…' : 'Submit decision'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Attached Evidence Items */}
                  {linkedEvidence.length > 0 && (
                    <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid #F1F5F9', display: 'grid', gap: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#64748B' }}>
                        Attached Immutable Evidence ({linkedEvidence.length})
                      </span>

                      {linkedEvidence.map(ev => {
                        const isContradiction = ev.relationship === 'CONTRADICTS' || (obligation.counter_evidence_ids || []).includes(ev.id)
                        return (
                          <div 
                            key={ev.id} 
                            style={{ 
                              padding: 10, 
                              borderRadius: 6, 
                              background: isContradiction ? '#FEF2F2' : '#F8FAFC', 
                              border: `1px solid ${isContradiction ? '#FECACA' : '#E2E8F0'}`,
                              display: 'grid',
                              gap: 6,
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
                              <strong style={{ fontSize: 12, color: '#0F172A', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                                <FileText size={12} color="#EA580C" />
                                {ev.path || 'Repository fact'}{ev.start_line ? `:${ev.start_line}-${ev.end_line}` : ''}
                              </strong>

                              <span 
                                className="badge-pill-base" 
                                style={{ 
                                  fontSize: 10, 
                                  background: isContradiction ? '#FEE2E2' : '#DCFCE7', 
                                  color: isContradiction ? '#991B1B' : '#166534',
                                  borderColor: isContradiction ? '#FCA5A5' : '#86EFAC',
                                }}
                              >
                                {isContradiction ? 'Contradicts claim' : 'Supports claim'}
                              </span>
                            </div>

                            <p style={{ fontSize: 12, color: '#334155', margin: 0 }}>
                              {ev.safe_fact_summary || ev.summary}
                            </p>

                            {ev.snippet && (
                              <pre 
                                style={{ 
                                  margin: '4px 0 0', 
                                  padding: 8, 
                                  background: '#FFFFFF', 
                                  border: '1px solid #E2E8F0', 
                                  borderRadius: 4, 
                                  fontFamily: 'var(--font-mono)', 
                                  fontSize: 11, 
                                  color: '#0F172A',
                                  overflowX: 'auto',
                                }}
                              >
                                {ev.snippet}
                              </pre>
                            )}

                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 10, color: '#94A3B8' }}>
                              <span>Tool execution: {ev.source_tool_run_id.slice(0, 8)}</span>
                              <span>·</span>
                              <span>Hash: {ev.content_hash?.slice(0, 10) || 'n/a'}</span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Updated Implementation Plan Section */}
      <div id="updated-implementation-plan" className="card-panel-white">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <div style={{ display: 'grid', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <div style={{ width: 28, height: 28, borderRadius: 6, background: '#FFF7ED', border: '1px solid #FFEDD5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Sparkles size={16} color="#EA580C" />
              </div>
              <strong style={{ fontSize: 16, color: '#0F172A' }}>
                Updated Implementation Plan
              </strong>
              {revisedPlan && (
                <span className="commit-mini-tag" style={{ background: '#F1F5F9', color: '#475569', fontWeight: 600 }}>
                  v{revisedPlan.revision_version}
                </span>
              )}
              {revisedPlan && (
                <span 
                  className="badge-pill-base" 
                  style={{
                    fontSize: 11,
                    background: revisedPlan.status === 'EVIDENCE_GROUNDED' ? '#ECFDF5' : revisedPlan.status === 'AWAITING_HUMAN_DECISION' ? '#FEF3C7' : revisedPlan.status === 'PROVISIONAL' ? '#F0F9FF' : '#F1F5F9',
                    color: revisedPlan.status === 'EVIDENCE_GROUNDED' ? '#065F46' : revisedPlan.status === 'AWAITING_HUMAN_DECISION' ? '#92400E' : revisedPlan.status === 'PROVISIONAL' ? '#075985' : '#475569',
                    borderColor: revisedPlan.status === 'EVIDENCE_GROUNDED' ? '#A7F3D0' : revisedPlan.status === 'AWAITING_HUMAN_DECISION' ? '#FDE68A' : revisedPlan.status === 'PROVISIONAL' ? '#BAE6FD' : '#CBD5E1',
                  }}
                >
                  {revisedPlan.status.replaceAll('_', ' ')}
                </span>
              )}
            </div>
            <span style={{ fontSize: 12.5, color: '#64748B' }}>
              Evidence-grounded implementation steps synthesized from verified immutable repository facts.
            </span>
          </div>

          {revisedPlan && revisedPlan.status !== 'UNAVAILABLE' && (
            <button
              type="button"
              className="btn-verify-plan-cta"
              style={{ fontSize: 12, padding: '7px 14px', display: 'inline-flex', alignItems: 'center', gap: 6 }}
              onClick={() => void handleCopyUpdatedPlan()}
            >
              {copiedPlan ? (
                <>
                  <Check size={14} /> Copied!
                </>
              ) : (
                <>
                  <Copy size={14} /> Copy Updated Plan
                </>
              )}
            </button>
          )}
        </div>

        {!revisedPlan ? (
          <div style={{ padding: 16, borderRadius: 8, background: '#F8FAFC', border: '1px solid #E2E8F0', fontSize: 12.5, color: '#64748B' }}>
            Updated implementation plan synthesis is available on newly executed verification runs. The deterministic Gate Report above contains all verified repository facts.
          </div>
        ) : revisedPlan.status === 'UNAVAILABLE' ? (
          <div style={{ padding: 16, borderRadius: 8, background: '#FEF2F2', border: '1px solid #FECACA', color: '#991B1B', fontSize: 12.5 }}>
            <strong style={{ display: 'block', marginBottom: 4 }}>Plan Revision Unavailable</strong>
            Model revision synthesis did not satisfy strict evidence citation invariants or provider gateway limits. The deterministic Gate Report above remains 100% authoritative.
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 18 }}>
            {/* Status Notice if Awaiting Human Decision */}
            {revisedPlan.status === 'AWAITING_HUMAN_DECISION' && (
              <div style={{ padding: 12, borderRadius: 6, background: '#FFFBEB', border: '1px solid #FDE68A', display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: '#92400E' }}>
                <Clock size={15} color="#D97706" />
                <span>
                  <strong>Preliminary Draft (v{revisedPlan.revision_version}):</strong> Plan synthesized before human decision resolution. A final revision will be generated once all open questions are answered.
                </span>
              </div>
            )}

            {/* Metrics Row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10 }}>
              <div style={{ padding: '10px 14px', borderRadius: 6, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>Total Steps</span>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', marginTop: 2 }}>{revisedPlan.implementation_plan?.length || 0}</div>
              </div>
              <div style={{ padding: '10px 14px', borderRadius: 6, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>Retained</span>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#334155', marginTop: 2 }}>
                  {revisedPlan.implementation_plan?.filter(s => s.status === 'KEEP').length || 0}
                </div>
              </div>
              <div style={{ padding: '10px 14px', borderRadius: 6, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, color: '#D97706', fontWeight: 600, textTransform: 'uppercase' }}>Modified</span>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#D97706', marginTop: 2 }}>
                  {revisedPlan.implementation_plan?.filter(s => s.status === 'MODIFY').length || 0}
                </div>
              </div>
              <div style={{ padding: '10px 14px', borderRadius: 6, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, color: '#DC2626', fontWeight: 600, textTransform: 'uppercase' }}>Removed</span>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#DC2626', marginTop: 2 }}>
                  {revisedPlan.plan_changes?.filter(c => c.change_type === 'REMOVE').length || 0}
                </div>
              </div>
              <div style={{ padding: '10px 14px', borderRadius: 6, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, color: '#16A34A', fontWeight: 600, textTransform: 'uppercase' }}>Added</span>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#16A34A', marginTop: 2 }}>
                  {revisedPlan.implementation_plan?.filter(s => s.status === 'ADD').length || 0}
                </div>
              </div>
            </div>

            {/* Executive Summary */}
            {revisedPlan.executive_summary && (
              <div style={{ padding: 14, borderRadius: 6, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                <strong style={{ fontSize: 12, color: '#0F172A', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Revision Summary
                </strong>
                <p style={{ fontSize: 13, color: '#334155', margin: 0, lineHeight: 1.5 }}>
                  {revisedPlan.executive_summary}
                </p>
              </div>
            )}

            {/* Plan Changes / Diffs */}
            {revisedPlan.plan_changes && revisedPlan.plan_changes.length > 0 && (
              <div style={{ display: 'grid', gap: 10 }}>
                <strong style={{ fontSize: 13, color: '#0F172A', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Plan Modifications &amp; Rationale ({revisedPlan.plan_changes.length})
                </strong>
                <div style={{ display: 'grid', gap: 8 }}>
                  {revisedPlan.plan_changes.map((chg, idx) => {
                    const isRemoved = chg.change_type === 'REMOVE'
                    const isModified = chg.change_type === 'MODIFY'
                    const isAdded = chg.change_type === 'ADD'
                    const bg = isRemoved ? '#FEF2F2' : isModified ? '#FFFBEB' : isAdded ? '#F0FDF4' : '#F8FAFC'
                    const border = isRemoved ? '#FECACA' : isModified ? '#FDE68A' : isAdded ? '#BBF7D0' : '#E2E8F0'
                    const tagBg = isRemoved ? '#FEE2E2' : isModified ? '#FEF3C7' : isAdded ? '#DCFCE7' : '#E2E8F0'
                    const tagColor = isRemoved ? '#991B1B' : isModified ? '#92400E' : isAdded ? '#166534' : '#475569'

                    return (
                      <div key={idx} style={{ padding: 12, borderRadius: 6, background: bg, border: `1px solid ${border}`, display: 'grid', gap: 6 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
                          <span style={{ fontSize: 12.5, fontWeight: 700, color: '#0F172A' }}>
                            {chg.source_plan_step_ids?.length ? `Step ${chg.source_plan_step_ids.join(', ')}: ` : ''}
                            {chg.updated_text ? chg.updated_text.slice(0, 80) : chg.original_text ? chg.original_text.slice(0, 80) : 'Step Modification'}
                          </span>
                          <span className="badge-pill-base" style={{ fontSize: 10, background: tagBg, color: tagColor, borderColor: 'transparent' }}>
                            {chg.change_type}
                          </span>
                        </div>

                        {chg.original_text && isModified && (
                          <div style={{ fontSize: 12, color: '#64748B', background: 'rgba(0,0,0,0.02)', padding: '6px 8px', borderRadius: 4 }}>
                            <span style={{ fontWeight: 600 }}>Original:</span> {chg.original_text}
                          </div>
                        )}

                        <p style={{ fontSize: 12.5, color: '#334155', margin: 0 }}>
                          <strong>Rationale:</strong> {chg.rationale}
                        </p>

                        {chg.basis_fact_ids && chg.basis_fact_ids.length > 0 && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                            <span style={{ fontSize: 11, color: '#64748B', fontWeight: 600 }}>Cites Facts:</span>
                            {chg.basis_fact_ids.map(fid => (
                              <span key={fid} className="commit-mini-tag" style={{ background: '#FFFFFF', border: '1px solid #CBD5E1', fontSize: 10.5 }}>
                                {fid.slice(0, 10)}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Ordered Implementation Steps */}
            {revisedPlan.implementation_plan && revisedPlan.implementation_plan.length > 0 && (
              <div style={{ display: 'grid', gap: 12 }}>
                <strong style={{ fontSize: 13, color: '#0F172A', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Ordered Implementation Steps ({revisedPlan.implementation_plan.length})
                </strong>

                <div style={{ display: 'grid', gap: 12 }}>
                  {revisedPlan.implementation_plan.map((step) => (
                    <div 
                      key={step.order} 
                      style={{ 
                        padding: 16, 
                        borderRadius: 8, 
                        background: '#FFFFFF', 
                        border: '1px solid #E2E8F0',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
                        display: 'grid',
                        gap: 10,
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span 
                            style={{ 
                              width: 24, 
                              height: 24, 
                              borderRadius: '50%', 
                              background: '#EA580C', 
                              color: '#FFFFFF', 
                              display: 'flex', 
                              alignItems: 'center', 
                              justifyContent: 'center', 
                              fontSize: 12, 
                              fontWeight: 700 
                            }}
                          >
                            {step.order}
                          </span>
                          <strong style={{ fontSize: 13.5, color: '#0F172A' }}>
                            {step.action}
                          </strong>
                        </div>

                        {step.status && (
                          <span className="badge-pill-base" style={{ fontSize: 10, background: '#F1F5F9', color: '#475569' }}>
                            {step.status}
                          </span>
                        )}
                      </div>

                      {/* File Target Badges */}
                      {((step.existing_target_files && step.existing_target_files.length > 0) || (step.proposed_new_files && step.proposed_new_files.length > 0)) && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                          {step.existing_target_files?.map(f => (
                            <span 
                              key={f} 
                              className="commit-mini-tag" 
                              style={{ 
                                background: '#F0FDF4', 
                                color: '#166534', 
                                borderColor: '#BBF7D0', 
                                display: 'inline-flex', 
                                alignItems: 'center', 
                                gap: 4, 
                                fontSize: 11 
                              }}
                            >
                              <FileText size={11} color="#16A34A" /> {f}
                            </span>
                          ))}
                          {step.proposed_new_files?.map(f => (
                            <span 
                              key={f} 
                              className="commit-mini-tag" 
                              style={{ 
                                background: '#EFF6FF', 
                                color: '#1E40AF', 
                                borderColor: '#BFDBFE', 
                                display: 'inline-flex', 
                                alignItems: 'center', 
                                gap: 4, 
                                fontSize: 11 
                              }}
                            >
                              + {f} (new)
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Step Rationale */}
                      {step.rationale && (
                        <div style={{ fontSize: 12.5, color: '#334155', lineHeight: 1.5, background: '#F8FAFC', padding: 10, borderRadius: 6, border: '1px solid #F1F5F9' }}>
                          {step.rationale}
                        </div>
                      )}

                      {/* Basis Facts Cited */}
                      {step.basis_fact_ids && step.basis_fact_ids.length > 0 && (
                        <div style={{ display: 'grid', gap: 4, paddingTop: 6, borderTop: '1px dashed #E2E8F0' }}>
                          <span style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', color: '#94A3B8' }}>
                            Cites Verified Evidence ({step.basis_fact_ids.length})
                          </span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                            {step.basis_fact_ids.map(fid => (
                              <span key={fid} className="commit-mini-tag" style={{ background: '#FFFFFF', border: '1px solid #CBD5E1', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                <ShieldCheck size={12} color="#16A34A" /> {fid.slice(0, 12)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tool Executions Trace Table */}
      <div className="card-panel-white">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div>
            <strong style={{ fontSize: 14.5, color: '#0F172A', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Terminal size={15} color="#EA580C" />
              Persisted Tool Executions ({projection.tool_runs.length})
            </strong>
            <span style={{ fontSize: 11.5, color: '#64748B' }}>
              Exact deterministic telemetry recorded for this verification run
            </span>
          </div>

          <Link href="/workspace/tool-traces" style={{ fontSize: 12, color: '#EA580C', fontWeight: 600, textDecoration: 'none' }}>
            Open Trace Explorer →
          </Link>
        </div>

        {projection.tool_runs.length === 0 ? (
          <p style={{ fontSize: 12.5, color: '#64748B' }}>
            {projection.trace_attribution_status === 'LEGACY_TRACE_UNAVAILABLE'
              ? 'Legacy trace telemetry attribution unavailable for this historical run.'
              : 'No tool executions recorded for this run.'}
          </p>
        ) : (
          <div style={{ display: 'grid', gap: 8 }}>
            {projection.tool_runs.map((tool, idx) => (
              <div 
                key={tool.id || idx} 
                style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center', 
                  padding: '8px 12px', 
                  borderRadius: 6, 
                  background: '#F8FAFC', 
                  border: '1px solid #E2E8F0',
                  fontSize: 12,
                  flexWrap: 'wrap',
                  gap: 8,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Wrench size={13} color="#64748B" />
                  <strong style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{tool.tool_name}</strong>
                  {tool.input_summary?.query && (
                    <span style={{ color: '#64748B', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                      query: &quot;{String(tool.input_summary.query)}&quot;
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ color: '#64748B', fontSize: 11 }}>
                    {tool.result_count} results · {tool.duration_ms} ms
                  </span>
                  <span className="commit-mini-tag">{tool.status}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

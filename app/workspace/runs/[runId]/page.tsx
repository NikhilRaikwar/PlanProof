'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { api, ApiError, Evidence, Obligation, RunProjection } from '@/lib/api'

const terminal = new Set(['COMPLETE', 'BLOCKED', 'INCONCLUSIVE', 'FAILED', 'HUMAN_DECISION_REQUIRED'])
const eventTypes = ['run_created', 'obligations_extracted', 'obligation_started', 'tool_started', 'tool_completed', 'tool_failed', 'evidence_added', 'human_question_created', 'human_answered', 'obligation_completed', 'run_completed', 'run_failed']

export default function RunReportPage() {
  const { runId } = useParams<{ runId: string }>()
  const [projection, setProjection] = useState<RunProjection | null>(null)
  const [obligations, setObligations] = useState<Obligation[]>([])
  const [evidence, setEvidence] = useState<Evidence[]>([])
  const [events, setEvents] = useState<string[]>([])
  const [streamState, setStreamState] = useState<'connecting' | 'live' | 'reconnecting'>('connecting')
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState('')
  const load = async () => { try { const [p, o, e] = await Promise.all([api.run(runId), api.obligations(runId), api.evidence(runId)]); setProjection(p); setObligations(o); setEvidence(e) } catch (x) { setError(x instanceof ApiError ? x.message : 'Could not load run report.') } }
  useEffect(() => { void load() }, [runId])
  // SSE delivers progress eagerly; this small persisted-projection refresh is
  // the recovery path for a completed/reconnected stream.  It never simulates
  // verification and stops for every authoritative terminal gate.
  useEffect(() => {
    if (!projection || terminal.has(projection.run.status)) return
    const timer = window.setTimeout(() => { void load() }, 2_000)
    return () => window.clearTimeout(timer)
  }, [projection, runId])
  useEffect(() => {
    if (!projection || terminal.has(projection.run.status)) return
    const source = new EventSource(api.eventsUrl(runId))
    source.onopen = () => setStreamState('live')
    const receive = (event: MessageEvent) => {
      setEvents(old => old.some(item => item.startsWith(`${event.lastEventId}:`)) ? old : [...old, `${event.lastEventId}:${event.data}`])
      void load()
    }
    eventTypes.forEach(type => source.addEventListener(type, receive))
    // EventSource performs its own bounded reconnect. Event IDs are de-duplicated
    // above, and every event triggers a fresh persisted projection fetch.
    source.onerror = () => setStreamState('reconnecting')
    return () => source.close()
  }, [projection, runId])
  const submit = async (id: string) => { try { await api.answer(id, answer); setAnswer(''); await load() } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not submit answer.') } }
  if (error) return <div className="card-panel-white" style={{ color: '#B91C1C' }}>{error}</div>
  if (!projection) return <div className="card-panel-white">Loading run report…</div>
  const { run } = projection
  return <div style={{ display: 'grid', gap: 18 }}>
    <div><div className="preflight-eyebrow"><span>PRE-FLIGHT GATE REPORT · SNAPSHOT {run.snapshot_id.slice(0, 7)}</span></div><h1 className="page-main-title">{run.status.replaceAll('_', ' ')}</h1><p className="page-main-desc">The gate and obligation statuses come from the persisted verification workflow.</p></div>
    <div className="card-panel-white"><strong>Gate: {run.status}</strong><div style={{ display: 'flex', gap: 14, marginTop: 10, fontSize: 12 }}>{Object.entries(projection.obligation_counts).map(([status, count]) => <span key={status}>{status}: {count}</span>)}</div><p style={{ fontSize: 12, color: '#64748B' }}>Evidence: {projection.evidence_count} · Tool calls: {run.tool_call_count} · Model calls: {run.model_call_count}</p></div>
    {events.length > 0 && <div className="card-panel-white"><strong>Live progress</strong><p style={{ fontSize: 12, color: '#64748B' }}>{streamState === 'live' ? 'Connected to persisted run events.' : 'Reconnecting to persisted run events…'}</p>{events.map(event => <p key={event} style={{ fontSize: 12 }}>{event}</p>)}</div>}
    <div className="card-panel-white"><h2>Proof obligations</h2>{obligations.length === 0 ? <p>No obligations have been extracted yet.</p> : obligations.map(item => <div key={item.id} style={{ padding: '12px 0', borderBottom: '1px solid #E2E8F0' }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><strong>{item.statement}</strong><span className="commit-mini-tag">{item.status}</span></div><p style={{ fontSize: 11, color: '#64748B' }}>{item.category} · {item.criticality}</p></div>)}</div>
    <div className="card-panel-white"><h2>Evidence</h2>{evidence.length === 0 ? <p>No evidence has been collected yet.</p> : evidence.map(item => <div key={item.id} style={{ padding: '10px 0', borderBottom: '1px solid #E2E8F0' }}><strong>{item.path || 'Repository fact'} {item.start_line ? `:${item.start_line}-${item.end_line}` : ''}</strong><p style={{ fontSize: 12 }}>{item.safe_fact_summary}</p><span style={{ fontSize: 10, color: '#64748B' }}>Tool {item.source_tool_run_id.slice(0, 8)} · {item.content_hash?.slice(0, 12)}</span></div>)}</div>
    {projection.human_questions.map(question => <div key={question.id} className="card-panel-white"><h2>Human decision required</h2><p>{question.question}</p><p style={{ fontSize: 12, color: '#64748B' }}>{question.why_needed} — {question.authority_required}</p><textarea className="custom-textarea" value={answer} onChange={e => setAnswer(e.target.value)} placeholder="Record the authorized decision…"/><button className="btn-verify-plan-cta" onClick={() => submit(question.id)}>Submit decision</button></div>)}
  </div>
}

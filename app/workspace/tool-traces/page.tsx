'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { 
  CheckCircle2, 
  ChevronDown, 
  ChevronRight, 
  Clock, 
  FileCode, 
  FolderGit2, 
  Info, 
  Layers3, 
  Search, 
  Terminal, 
  Wrench, 
  XCircle 
} from 'lucide-react'
import { api, ApiError, RunProjection, ToolRun, VerificationRun } from '@/lib/api'
import { useWorkspace } from '@/components/workspace-context'

export default function ToolTracesPage() {
  const { selectedRepo } = useWorkspace()
  const [runs, setRuns] = useState<VerificationRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState('')
  const [items, setItems] = useState<ToolRun[]>([])
  const [projection, setProjection] = useState<RunProjection | null>(null)
  const [loadingRuns, setLoadingRuns] = useState(false)
  const [loadingTraces, setLoadingTraces] = useState(false)
  const [error, setError] = useState('')
  const [expandedTraceId, setExpandedTraceId] = useState<string | null>(null)

  // 1. Fetch runs scoped to the selected repository
  useEffect(() => {
    if (!selectedRepo) {
      setRuns([])
      setSelectedRunId('')
      setItems([])
      setProjection(null)
      setLoadingRuns(false)
      return
    }
    setLoadingRuns(true)
    setError('')
    void api.runs(selectedRepo.repositoryId)
      .then(data => {
        setRuns(data)
        if (data.length > 0) {
          setSelectedRunId(data[0].id)
        } else {
          setSelectedRunId('')
          setItems([])
          setProjection(null)
        }
      })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load runs.'))
      .finally(() => setLoadingRuns(false))
  }, [selectedRepo?.repositoryId])

  // 2. Fetch tool runs and projection for the selected run
  useEffect(() => {
    if (!selectedRunId) {
      setItems([])
      setProjection(null)
      return
    }

    setLoadingTraces(true)
    setError('')
    void Promise.all([
      api.toolRuns(selectedRunId),
      api.run(selectedRunId).catch(() => null)
    ])
      .then(([traces, proj]) => {
        setItems(traces)
        setProjection(proj)
        if (traces.length > 0) {
          setExpandedTraceId(traces[0].id)
        }
      })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load tool traces.'))
      .finally(() => setLoadingTraces(false))
  }, [selectedRunId])

  const selectedRun = runs.find(r => r.id === selectedRunId)

  const getToolIcon = (toolName: string) => {
    if (toolName.includes('search')) return <Search size={14} color="#EA580C" />
    if (toolName.includes('file') || toolName.includes('symbol')) return <FileCode size={14} color="#3B82F6" />
    return <Wrench size={14} color="#64748B" />
  }

  return (
    <div style={{ display: 'grid', gap: 20 }}>
      {/* Page Header */}
      <div>
        <div className="preflight-eyebrow">
          <Terminal size={13} />
          <span>EXECUTION TELEMETRY</span>
        </div>
        <h1 className="page-main-title">Tool traces</h1>
        <p className="page-main-desc">
          {selectedRepo
            ? `Exact persisted tool execution records for ${selectedRepo.repositoryFullName}.`
            : 'Select a repository to view execution telemetry.'}
        </p>
      </div>

      {error ? (
        <div className="card-panel-white" style={{ color: '#B91C1C', borderColor: '#FCA5A5', background: '#FEF2F2', padding: 16 }}>{error}</div>
      ) : loadingRuns ? (
        <div className="card-panel-white" style={{ textAlign: 'center', padding: 40, color: '#64748B' }}>
          Loading verification runs{selectedRepo ? ` for ${selectedRepo.repositoryFullName}` : ''}…
        </div>
      ) : !selectedRepo ? (
        <div className="card-panel-white" style={{ textAlign: 'center', padding: '56px 24px' }}>
          <FolderGit2 size={38} style={{ color: '#EA580C', margin: '0 auto 14px' }} />
          <h2 style={{ fontSize: 17, fontWeight: 750, color: '#0F172A', marginBottom: 6 }}>
            Select a repository to view tool traces.
          </h2>
          <p style={{ fontSize: 13, color: '#64748B', maxWidth: 440, margin: '0 auto 20px' }}>
            Choose an active connected repository to inspect its exact persisted tool executions.
          </p>
          <Link href="/workspace/repositories" className="btn-verify-plan-cta">
            Select repository
          </Link>
        </div>
      ) : runs.length === 0 ? (
        <div className="card-panel-white" style={{ textAlign: 'center', padding: '56px 24px' }}>
          <Layers3 size={38} style={{ color: '#EA580C', margin: '0 auto 14px' }} />
          <h2 style={{ fontSize: 17, fontWeight: 750, color: '#0F172A', marginBottom: 6 }}>
            No verification runs yet for {selectedRepo.repositoryFullName}
          </h2>
          <p style={{ fontSize: 13, color: '#64748B', maxWidth: 440, margin: '0 auto 20px' }}>
            Verify an engineering plan to generate deterministic execution telemetry.
          </p>
          <Link href={`/workspace/new-verification${selectedRepo.snapshotId ? `?snapshot_id=${selectedRepo.snapshotId}` : ''}`} className="btn-verify-plan-cta">
            Start verification
          </Link>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 16 }}>
          {/* Run Selector Scoped to Selected Repository */}
          <div className="card-panel-white" style={{ padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', flex: 1 }}>
              <label htmlFor="trace-run-select" style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', whiteSpace: 'nowrap' }}>
                Run selector:
              </label>
              <select
                id="trace-run-select"
                className="custom-select-box"
                style={{ maxWidth: 520, height: 38, fontSize: 12.5 }}
                value={selectedRunId}
                onChange={e => setSelectedRunId(e.target.value)}
              >
                {runs.map(r => (
                  <option key={r.id} value={r.id}>
                    run-{r.id.slice(0, 8)} · [{r.status}] · {r.plan_title ? r.plan_title.slice(0, 50) : new Date(r.created_at).toLocaleDateString()}
                  </option>
                ))}
              </select>
            </div>

            {selectedRunId && (
              <Link 
                href={`/workspace/runs/${selectedRunId}`} 
                style={{ fontSize: 12, color: '#EA580C', fontWeight: 650, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                <span>View full gate report</span>
                <span>→</span>
              </Link>
            )}
          </div>

          {/* Attribution Notice */}
          {projection?.trace_attribution_status === 'LEGACY_EVIDENCE_RECONSTRUCTED' && (
            <div className="card-panel-subtle" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', fontSize: 12, color: '#475569' }}>
              <Info size={14} color="#0284C7" />
              <span>
                Historical run: showing exact tool executions bound through server-issued evidence records.
              </span>
            </div>
          )}

          {projection?.trace_attribution_status === 'LEGACY_TRACE_UNAVAILABLE' && (
            <div className="card-panel-subtle" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', fontSize: 12, color: '#D97706', background: '#FFFBEB', borderColor: '#FDE68A' }}>
              <Info size={14} color="#D97706" />
              <span>
                Legacy trace attribution unavailable: this historical run did not capture exact run-level tool execution linkages.
              </span>
            </div>
          )}

          {/* Trace List with In-Place Expansion */}
          {loadingTraces ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 40, color: '#64748B' }}>
              Loading execution telemetry…
            </div>
          ) : items.length === 0 ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 48, color: '#64748B' }}>
              <Terminal size={32} style={{ color: '#94A3B8', margin: '0 auto 10px' }} />
              <strong style={{ display: 'block', color: '#0F172A', fontSize: 14, marginBottom: 4 }}>
                No tool executions were recorded for this run.
              </strong>
              <p style={{ fontSize: 12.5, margin: 0 }}>
                {selectedRun?.status === 'FAILED'
                  ? 'The verification ended before repository investigation completed.'
                  : 'The run did not trigger bounded tool execution steps.'}
              </p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              {items.map((t, idx) => {
                const isFailed = t.status === 'FAILED'
                const isExpanded = expandedTraceId === t.id
                const summary = t.input_summary

                return (
                  <article
                    key={t.id}
                    className="card-panel-white"
                    style={{
                      padding: 0,
                      borderColor: isFailed ? '#FCA5A5' : isExpanded ? '#CBD5E1' : '#E2E8F0',
                      background: isFailed ? '#FEF2F2' : '#FFFFFF',
                      overflow: 'hidden',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {/* Header Row / Toggle */}
                    <div
                      onClick={() => setExpandedTraceId(isExpanded ? null : t.id)}
                      style={{
                        padding: '14px 18px',
                        cursor: 'pointer',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: 12,
                        userSelect: 'none',
                        background: isExpanded ? '#F8FAFC' : 'transparent',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 260 }}>
                        {isExpanded ? <ChevronDown size={15} color="#64748B" /> : <ChevronRight size={15} color="#64748B" />}
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, fontWeight: 700, color: '#0F172A' }}>
                          {getToolIcon(t.tool_name)}
                          <code>{t.tool_name}</code>
                          <span style={{ fontSize: 11, color: '#94A3B8', fontWeight: 500 }}>#{idx + 1}</span>
                        </span>

                        {summary?.query && (
                          <span className="commit-mini-tag" style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            &quot;{summary.query}&quot;
                          </span>
                        )}

                        {summary?.path && (
                          <span style={{ fontSize: 11.5, color: '#64748B', fontFamily: 'var(--font-mono)' }}>
                            {summary.path}
                          </span>
                        )}
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 11.5, color: '#64748B' }}>
                          <Clock size={11} /> {t.duration_ms}ms
                        </span>

                        <span style={{ fontSize: 11.5, color: '#64748B' }}>
                          {t.result_count} {t.result_count === 1 ? 'match' : 'matches'}
                        </span>

                        <span className={`badge-pill-base ${isFailed ? 'badge-blocked' : 'badge-verified'}`} style={{ fontSize: 10.5 }}>
                          {isFailed ? <XCircle size={11} /> : <CheckCircle2 size={11} />}
                          {t.status}
                        </span>
                      </div>
                    </div>

                    {/* Expanded Detail View In Place */}
                    {isExpanded && (
                      <div style={{ padding: 18, borderTop: '1px solid #E2E8F0', display: 'grid', gap: 14 }}>
                        {/* Parameter Summary */}
                        <div style={{ display: 'grid', gap: 6 }}>
                          <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#64748B' }}>
                            Safe Execution Inputs
                          </span>
                          <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 6, padding: '10px 14px', fontSize: 12, fontFamily: 'var(--font-mono)', color: '#0F172A', display: 'grid', gap: 4 }}>
                            {summary ? (
                              Object.entries(summary).map(([k, v]) => (
                                <div key={k} style={{ display: 'flex', gap: 8 }}>
                                  <strong style={{ color: '#64748B', minWidth: 90 }}>{k}:</strong>
                                  <span>{String(v)}</span>
                                </div>
                              ))
                            ) : (
                              <span>input_hash: {t.input_hash}</span>
                            )}
                          </div>
                        </div>

                        {/* Error info if failed */}
                        {isFailed && (
                          <div style={{ background: '#FEF2F2', border: '1px solid #FCA5A5', borderRadius: 6, padding: '10px 14px', fontSize: 12, color: '#991B1B' }}>
                            <strong>Execution Failure:</strong> {t.safe_error_class || 'TOOL_FAILURE'}
                          </div>
                        )}

                        {/* Telemetry metadata footer */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: '#94A3B8', flexWrap: 'wrap', paddingTop: 8, borderTop: '1px solid #F1F5F9' }}>
                          <span>Trace ID: <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{t.id}</code></span>
                          <span>·</span>
                          <span>Snapshot: <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{t.snapshot_id ? t.snapshot_id.slice(0, 7) : 'n/a'}</code></span>
                          {t.run_id && (
                            <>
                              <span>·</span>
                              <span>Run ID: <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{t.run_id.slice(0, 8)}</code></span>
                            </>
                          )}
                          <span>·</span>
                          <span>Executed: {new Date(t.started_at).toLocaleTimeString()}</span>
                        </div>
                      </div>
                    )}
                  </article>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

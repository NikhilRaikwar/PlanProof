'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { 
  CheckCircle2, 
  Clock, 
  FolderGit2, 
  Layers3, 
  Terminal, 
  Wrench, 
  XCircle, 
  Search, 
  FileCode, 
  Info 
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
      })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load tool traces.'))
      .finally(() => setLoadingTraces(false))
  }, [selectedRunId])

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
          <div className="card-panel-white" style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <label htmlFor="trace-run-select" style={{ fontSize: 13, fontWeight: 700, color: '#0F172A' }}>
              Verification Run:
            </label>
            <select
              id="trace-run-select"
              className="custom-select-box"
              style={{ maxWidth: 460 }}
              value={selectedRunId}
              onChange={e => setSelectedRunId(e.target.value)}
            >
              {runs.map(r => (
                <option key={r.id} value={r.id}>
                  run-{r.id.slice(0, 8)} · {r.status} · {r.plan_title ? r.plan_title.slice(0, 45) : new Date(r.created_at).toLocaleDateString()}
                </option>
              ))}
            </select>

            {selectedRunId && (
              <Link href={`/workspace/runs/${selectedRunId}`} style={{ fontSize: 12, color: '#EA580C', fontWeight: 650, textDecoration: 'none' }}>
                View full gate report →
              </Link>
            )}
          </div>

          {error && <div className="card-panel-white" style={{ color: '#B91C1C' }}>{error}</div>}

          {loadingTraces ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 40, color: '#64748B' }}>
              Loading execution telemetry…
            </div>
          ) : items.length === 0 ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 48, color: '#64748B' }}>
              {projection?.trace_attribution_status === 'LEGACY_TRACE_UNAVAILABLE'
                ? 'Legacy trace telemetry attribution unavailable for this historical run.'
                : 'No tool executions recorded for this verification run.'}
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, color: '#64748B', padding: '0 4px' }}>
                <span>Showing <strong>{items.length}</strong> persisted tool executions</span>
                {projection?.trace_attribution_status && (
                  <span style={{ fontSize: 11, background: '#F1F5F9', padding: '2px 8px', borderRadius: 4 }}>
                    Attribution: {projection.trace_attribution_status}
                  </span>
                )}
              </div>

              {items.map((item, idx) => {
                const isSuccess = item.status === 'SUCCEEDED'
                const summary = item.input_summary || {}

                return (
                  <article 
                    key={item.id || idx} 
                    className="card-panel-white" 
                    style={{ padding: 16, display: 'grid', gap: 10 }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {getToolIcon(item.tool_name)}
                        <strong style={{ fontFamily: 'var(--font-mono)', fontSize: 13.5, color: '#0F172A' }}>
                          {item.tool_name}
                        </strong>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {isSuccess ? (
                          <span className="badge-pill-base badge-verified" style={{ fontSize: 10.5 }}>
                            <CheckCircle2 size={12} /> SUCCEEDED
                          </span>
                        ) : (
                          <span className="badge-pill-base badge-blocked" style={{ fontSize: 10.5 }}>
                            <XCircle size={12} /> FAILED
                          </span>
                        )}
                        <span style={{ fontSize: 11, color: '#64748B', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                          <Clock size={11} /> {item.duration_ms} ms
                        </span>
                      </div>
                    </div>

                    {/* Safe Sanitized Input Summary */}
                    {Object.keys(summary).length > 0 && (
                      <div style={{ background: '#F8FAFC', padding: 10, borderRadius: 6, border: '1px solid #E2E8F0', display: 'grid', gap: 4, fontSize: 12 }}>
                        {summary.query && (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <span style={{ color: '#64748B', fontWeight: 600 }}>Query:</span>
                            <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>&quot;{String(summary.query)}&quot;</code>
                          </div>
                        )}
                        {summary.path && (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <span style={{ color: '#64748B', fontWeight: 600 }}>Path:</span>
                            <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{String(summary.path)}</code>
                          </div>
                        )}
                        {summary.name && (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <span style={{ color: '#64748B', fontWeight: 600 }}>Symbol:</span>
                            <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{String(summary.name)}</code>
                          </div>
                        )}
                        {summary.line_range && (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <span style={{ color: '#64748B', fontWeight: 600 }}>Lines:</span>
                            <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{String(summary.line_range)}</code>
                          </div>
                        )}
                      </div>
                    )}

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: '#94A3B8', flexWrap: 'wrap', gap: 8, paddingTop: 4 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span>Results: <strong style={{ color: '#0F172A' }}>{item.result_count}</strong></span>
                        <span>·</span>
                        <span>Fingerprint: <code style={{ fontFamily: 'var(--font-mono)' }}>{item.input_hash.slice(0, 12)}</code></span>
                        {item.safe_error_class && (
                          <>
                            <span>·</span>
                            <span style={{ color: '#DC2626' }}>Error: {item.safe_error_class}</span>
                          </>
                        )}
                      </div>

                      {item.started_at && (
                        <span>{new Date(item.started_at).toLocaleTimeString()}</span>
                      )}
                    </div>
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

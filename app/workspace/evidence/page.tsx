'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { 
  CheckCircle2, 
  Code2, 
  FileText, 
  FolderGit2, 
  GitBranch, 
  GitCommit, 
  Layers3, 
  ShieldAlert, 
  Wrench, 
  XCircle 
} from 'lucide-react'
import { api, ApiError, Evidence, VerificationRun } from '@/lib/api'
import { useWorkspace } from '@/components/workspace-context'

export default function EvidencePage() {
  const { selectedRepo } = useWorkspace()
  const [runs, setRuns] = useState<VerificationRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState('')
  const [items, setItems] = useState<Evidence[]>([])
  const [loadingRuns, setLoadingRuns] = useState(false)
  const [loadingEvidence, setLoadingEvidence] = useState(false)
  const [error, setError] = useState('')

  // 1. Fetch runs scoped to the selected repository
  useEffect(() => {
    if (!selectedRepo) {
      setRuns([])
      setSelectedRunId('')
      setItems([])
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
        }
      })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load runs.'))
      .finally(() => setLoadingRuns(false))
  }, [selectedRepo?.repositoryId])

  // 2. Fetch evidence for the selected run
  useEffect(() => {
    if (!selectedRunId) {
      setItems([])
      return
    }

    setLoadingEvidence(true)
    setError('')
    void api.evidence(selectedRunId)
      .then(data => setItems(data))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load evidence.'))
      .finally(() => setLoadingEvidence(false))
  }, [selectedRunId])

  // Group evidence by obligation
  const groupedEvidence: Record<string, { statement: string; items: Evidence[] }> = {}
  const unassociatedItems: Evidence[] = []

  items.forEach(item => {
    if (item.obligation_id) {
      if (!groupedEvidence[item.obligation_id]) {
        groupedEvidence[item.obligation_id] = {
          statement: item.obligation_statement || 'Proof obligation',
          items: [],
        }
      }
      groupedEvidence[item.obligation_id].items.push(item)
    } else {
      unassociatedItems.push(item)
    }
  })

  return (
    <div style={{ display: 'grid', gap: 20 }}>
      {/* Page Header */}
      <div>
        <div className="preflight-eyebrow">
          <FileText size={13} />
          <span>EVIDENCE EXPLORER</span>
        </div>
        <h1 className="page-main-title">Evidence explorer</h1>
        <p className="page-main-desc">
          {selectedRepo
            ? `Immutable, code-backed proof collected for ${selectedRepo.repositoryFullName}.`
            : 'Select a repository to inspect server-issued source facts.'}
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
            Select a repository to view evidence.
          </h2>
          <p style={{ fontSize: 13, color: '#64748B', maxWidth: 440, margin: '0 auto 20px' }}>
            Choose an active connected repository to inspect its immutable snapshot-backed facts and findings.
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
            Run a verification to produce server-issued evidence items.
          </p>
          <Link href={`/workspace/new-verification${selectedRepo.snapshotId ? `?snapshot_id=${selectedRepo.snapshotId}` : ''}`} className="btn-verify-plan-cta">
            Start verification
          </Link>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 16 }}>
          {/* Run Selector Scoped to Selected Repository */}
          <div className="card-panel-white" style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <label htmlFor="evidence-run-select" style={{ fontSize: 13, fontWeight: 700, color: '#0F172A' }}>
              Verification Run:
            </label>
            <select
              id="evidence-run-select"
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

          {loadingEvidence ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 40, color: '#64748B' }}>
              Loading evidence records…
            </div>
          ) : items.length === 0 ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 48, color: '#64748B' }}>
              No server-issued evidence has been produced for this verification run yet.
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 18 }}>
              {/* Evidence Grouped by Obligation */}
              {Object.entries(groupedEvidence).map(([obId, group]) => (
                <div key={obId} className="card-panel-white" style={{ display: 'grid', gap: 12 }}>
                  <div style={{ borderBottom: '1px solid #F1F5F9', paddingBottom: 10 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#64748B' }}>
                      Associated Proof Obligation
                    </span>
                    <h3 style={{ fontSize: 14.5, color: '#0F172A', margin: '4px 0 0', fontWeight: 700 }}>
                      {group.statement}
                    </h3>
                  </div>

                  <div style={{ display: 'grid', gap: 10 }}>
                    {group.items.map(ev => {
                      const isContradiction = ev.relationship === 'CONTRADICTS'
                      return (
                        <article 
                          key={ev.id} 
                          style={{ 
                            padding: 14, 
                            borderRadius: 8, 
                            background: isContradiction ? '#FEF2F2' : '#F8FAFC', 
                            border: `1px solid ${isContradiction ? '#FECACA' : '#E2E8F0'}`,
                            display: 'grid',
                            gap: 8,
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                            <strong style={{ fontSize: 13, color: '#0F172A', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                              <FileText size={14} color="#EA580C" />
                              {ev.path || 'Repository fact'}{ev.start_line ? `:${ev.start_line}-${ev.end_line}` : ''}
                            </strong>

                            <span 
                              className="badge-pill-base" 
                              style={{ 
                                fontSize: 10.5, 
                                background: isContradiction ? '#FEE2E2' : '#DCFCE7', 
                                color: isContradiction ? '#991B1B' : '#166534',
                                borderColor: isContradiction ? '#FCA5A5' : '#86EFAC',
                              }}
                            >
                              {isContradiction ? 'Contradicts claim' : 'Supports claim'}
                            </span>
                          </div>

                          <p style={{ fontSize: 12.5, color: '#334155', margin: 0, lineHeight: 1.4 }}>
                            {ev.safe_fact_summary || ev.summary}
                          </p>

                          {ev.snippet && (
                            <pre 
                              style={{ 
                                margin: 0, 
                                padding: 10, 
                                background: '#FFFFFF', 
                                border: '1px solid #E2E8F0', 
                                borderRadius: 6, 
                                fontFamily: 'var(--font-mono)', 
                                fontSize: 11.5, 
                                color: '#0F172A',
                                overflowX: 'auto',
                                lineHeight: 1.4,
                              }}
                            >
                              {ev.snippet}
                            </pre>
                          )}

                          <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: '#94A3B8', flexWrap: 'wrap' }}>
                            <span>Evidence ID: <code style={{ fontFamily: 'var(--font-mono)' }}>{ev.id.slice(0, 10)}</code></span>
                            <span>·</span>
                            <span>Snapshot: <code style={{ fontFamily: 'var(--font-mono)' }}>{ev.snapshot_id.slice(0, 7)}</code></span>
                            <span>·</span>
                            <span>Source tool: <code style={{ fontFamily: 'var(--font-mono)' }}>{ev.source_tool_run_id.slice(0, 8)}</code></span>
                            {ev.content_hash && (
                              <>
                                <span>·</span>
                                <span>Hash: <code style={{ fontFamily: 'var(--font-mono)' }}>{ev.content_hash.slice(0, 12)}</code></span>
                              </>
                            )}
                            {ev.created_at && (
                              <>
                                <span>·</span>
                                <span>{new Date(ev.created_at).toLocaleTimeString()}</span>
                              </>
                            )}
                          </div>
                        </article>
                      )
                    })}
                  </div>
                </div>
              ))}

              {/* Unassociated Items if any */}
              {unassociatedItems.length > 0 && (
                <div className="card-panel-white" style={{ display: 'grid', gap: 12 }}>
                  <h3 style={{ fontSize: 14.5, color: '#0F172A', margin: 0 }}>
                    Additional Snapshot Evidence ({unassociatedItems.length})
                  </h3>
                  <div style={{ display: 'grid', gap: 10 }}>
                    {unassociatedItems.map(ev => (
                      <article key={ev.id} style={{ padding: 12, borderRadius: 6, background: '#F8FAFC', border: '1px solid #E2E8F0', display: 'grid', gap: 6 }}>
                        <strong style={{ fontSize: 12.5, color: '#0F172A' }}>
                          {ev.path || 'Repository fact'}{ev.start_line ? `:${ev.start_line}-${ev.end_line}` : ''}
                        </strong>
                        <p style={{ fontSize: 12, color: '#334155', margin: 0 }}>
                          {ev.safe_fact_summary || ev.summary}
                        </p>
                      </article>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

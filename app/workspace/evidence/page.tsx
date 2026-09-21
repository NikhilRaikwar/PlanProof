'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { 
  CheckCircle2, 
  ChevronDown, 
  ChevronRight, 
  Code2, 
  FileText, 
  FolderGit2, 
  GitBranch, 
  GitCommit, 
  Layers3, 
  ShieldAlert, 
  ShieldCheck, 
  Terminal, 
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
  const [expandedId, setExpandedId] = useState<string | null>(null)

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
      .then(data => {
        setItems(data)
        if (data.length > 0) {
          setExpandedId(data[0].id)
        }
      })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load evidence.'))
      .finally(() => setLoadingEvidence(false))
  }, [selectedRunId])

  const selectedRun = runs.find(r => r.id === selectedRunId)

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
          <div className="card-panel-white" style={{ padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', flex: 1 }}>
              <label htmlFor="evidence-run-select" style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', whiteSpace: 'nowrap' }}>
                Run selector:
              </label>
              <select
                id="evidence-run-select"
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

          {loadingEvidence ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 40, color: '#64748B' }}>
              Loading evidence records…
            </div>
          ) : items.length === 0 ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 48, color: '#64748B' }}>
              <FileText size={32} style={{ color: '#94A3B8', margin: '0 auto 10px' }} />
              <strong style={{ display: 'block', color: '#0F172A', fontSize: 14, marginBottom: 4 }}>
                No server-issued evidence was produced for this run.
              </strong>
              <p style={{ fontSize: 12.5, margin: 0 }}>
                {selectedRun?.status === 'FAILED'
                  ? 'The verification run encountered a failure before repository investigation could complete.'
                  : 'The candidate plan claims did not yield matching source evidence within the investigation budget.'}
              </p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 18 }}>
              {/* Evidence Grouped by Obligation */}
              {Object.entries(groupedEvidence).map(([obId, group]) => (
                <div key={obId} className="card-panel-white" style={{ display: 'grid', gap: 14, padding: 18 }}>
                  <div style={{ borderBottom: '1px solid #F1F5F9', paddingBottom: 10 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#64748B', letterSpacing: '0.04em' }}>
                      Associated Proof Obligation
                    </span>
                    <h3 style={{ fontSize: 14.5, color: '#0F172A', margin: '4px 0 0', fontWeight: 700, lineHeight: 1.35 }}>
                      {group.statement}
                    </h3>
                  </div>

                  <div style={{ display: 'grid', gap: 10 }}>
                    {group.items.map(ev => {
                      const isContradiction = ev.relationship === 'CONTRADICTS'
                      const isExpanded = expandedId === ev.id

                      return (
                        <article 
                          key={ev.id} 
                          style={{ 
                            borderRadius: 8, 
                            background: isContradiction ? '#FEF2F2' : '#F8FAFC', 
                            border: `1px solid ${isContradiction ? '#FECACA' : '#E2E8F0'}`,
                            overflow: 'hidden',
                            transition: 'all 0.15s ease',
                          }}
                        >
                          {/* Card Header / In-Place Toggle */}
                          <div 
                            onClick={() => setExpandedId(isExpanded ? null : ev.id)}
                            style={{ 
                              padding: '12px 16px',
                              cursor: 'pointer',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              flexWrap: 'wrap',
                              gap: 10,
                              userSelect: 'none',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              {isExpanded ? <ChevronDown size={15} color="#64748B" /> : <ChevronRight size={15} color="#64748B" />}
                              <FileText size={15} color="#EA580C" />
                              <strong style={{ fontSize: 13, color: '#0F172A', fontFamily: 'var(--font-mono)' }}>
                                {ev.path || 'Repository fact'}{ev.start_line ? `:${ev.start_line}-${ev.end_line}` : ''}
                              </strong>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
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
                              <span style={{ fontSize: 11, color: '#94A3B8' }}>
                                {isExpanded ? 'Collapse' : 'Inspect details'}
                              </span>
                            </div>
                          </div>

                          {/* Expanded In-Place Details */}
                          {isExpanded && (
                            <div style={{ padding: '0 16px 16px', display: 'grid', gap: 12, borderTop: `1px solid ${isContradiction ? '#FEE2E2' : '#E2E8F0'}`, paddingTop: 12 }}>
                              <p style={{ fontSize: 13, color: '#334155', margin: 0, lineHeight: 1.45 }}>
                                {ev.safe_fact_summary || ev.summary}
                              </p>

                              {ev.snippet && (
                                <div style={{ display: 'grid', gap: 4 }}>
                                  <span style={{ fontSize: 11, fontWeight: 700, color: '#64748B', textTransform: 'uppercase' }}>
                                    Snapshot Source Snippet (Immutable)
                                  </span>
                                  <pre 
                                    style={{ 
                                      margin: 0, 
                                      padding: '12px 14px', 
                                      background: '#FFFFFF', 
                                      border: '1px solid #CBD5E1', 
                                      borderRadius: 6, 
                                      fontFamily: 'var(--font-mono)', 
                                      fontSize: 12, 
                                      color: '#0F172A',
                                      overflowX: 'auto',
                                      lineHeight: 1.45,
                                    }}
                                  >
                                    {ev.snippet}
                                  </pre>
                                </div>
                              )}

                              {/* Immutable Provenance Metadata */}
                              <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: '#64748B', flexWrap: 'wrap', background: '#FFFFFF', padding: '8px 12px', borderRadius: 6, border: '1px solid #E2E8F0' }}>
                                <span>Evidence ID: <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{ev.id}</code></span>
                                <span>·</span>
                                <span>Snapshot: <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{ev.snapshot_id.slice(0, 7)}</code></span>
                                <span>·</span>
                                <span>Source Tool: <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{ev.source_tool_run_id.slice(0, 8)}</code></span>
                                {ev.content_hash && (
                                  <>
                                    <span>·</span>
                                    <span>Content Hash: <code style={{ fontFamily: 'var(--font-mono)', color: '#0F172A' }}>{ev.content_hash.slice(0, 16)}</code></span>
                                  </>
                                )}
                              </div>
                            </div>
                          )}
                        </article>
                      )
                    })}
                  </div>
                </div>
              ))}

              {/* Unassociated Items if any */}
              {unassociatedItems.length > 0 && (
                <div className="card-panel-white" style={{ display: 'grid', gap: 12, padding: 18 }}>
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

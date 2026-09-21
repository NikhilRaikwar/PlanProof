'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { 
  Activity, 
  ArrowRight, 
  FolderGit2, 
  GitBranch, 
  GitCommit, 
  Layers3, 
  Plus, 
  ShieldAlert, 
  ShieldCheck, 
  Clock, 
  Wrench, 
  FileText 
} from 'lucide-react'
import { api, ApiError, VerificationRun } from '@/lib/api'
import { useWorkspace } from '@/components/workspace-context'

type FilterStatus = 'ALL' | 'BLOCKED' | 'COMPLETE' | 'HUMAN_WAIT' | 'INCONCLUSIVE' | 'FAILED'

export default function RunsPage() {
  const { selectedRepo } = useWorkspace()
  const [runs, setRuns] = useState<VerificationRun[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [activeFilter, setActiveFilter] = useState<FilterStatus>('ALL')

  useEffect(() => {
    if (!selectedRepo) {
      setRuns([])
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    void api.runs(selectedRepo.repositoryId)
      .then(data => setRuns(data))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load runs.'))
      .finally(() => setLoading(false))
  }, [selectedRepo?.repositoryId])

  const filterTabs: { key: FilterStatus; label: string }[] = [
    { key: 'ALL', label: 'All' },
    { key: 'BLOCKED', label: 'Blocked' },
    { key: 'COMPLETE', label: 'Passed / Complete' },
    { key: 'HUMAN_WAIT', label: 'Human required' },
    { key: 'INCONCLUSIVE', label: 'Inconclusive' },
    { key: 'FAILED', label: 'Failed' },
  ]

  const filteredRuns = runs.filter(run => {
    if (activeFilter === 'ALL') return true
    if (activeFilter === 'HUMAN_WAIT') {
      return run.status === 'HUMAN_WAIT' || run.status === 'HUMAN_DECISION_REQUIRED' || run.has_open_human_question
    }
    return run.status === activeFilter
  })

  const getStatusBadge = (status: string, hasHumanWait?: boolean | null) => {
    if (status === 'BLOCKED') {
      return <span className="badge-pill-base badge-blocked"><ShieldAlert size={12} /> BLOCKED</span>
    }
    if (status === 'COMPLETE') {
      return <span className="badge-pill-base badge-verified"><ShieldCheck size={12} /> COMPLETE</span>
    }
    if (status === 'HUMAN_WAIT' || status === 'HUMAN_DECISION_REQUIRED' || hasHumanWait) {
      return <span className="badge-pill-base" style={{ background: '#FEF3C7', color: '#92400E', borderColor: '#FDE68A' }}><Clock size={12} /> HUMAN WAIT</span>
    }
    if (status === 'INCONCLUSIVE') {
      return <span className="badge-pill-base badge-queued">INCONCLUSIVE</span>
    }
    if (status === 'FAILED') {
      return <span className="badge-pill-base badge-blocked">FAILED</span>
    }
    return <span className="badge-pill-base badge-queued">{status}</span>
  }

  return (
    <div style={{ display: 'grid', gap: 20 }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div className="preflight-eyebrow">
            <Activity size={13} />
            <span>VERIFICATION HISTORY</span>
          </div>
          <h1 className="page-main-title">Verification runs</h1>
          <p className="page-main-desc">
            {selectedRepo 
              ? `Scoped verification runs for ${selectedRepo.repositoryFullName}.`
              : 'Select a repository to view verification runs.'}
          </p>
        </div>

        {selectedRepo && (
          <Link href={`/workspace/new-verification${selectedRepo.snapshotId ? `?snapshot_id=${selectedRepo.snapshotId}` : ''}`} className="btn-verify-plan-cta">
            <Plus size={14} />
            New verification
          </Link>
        )}
      </div>

      {error ? (
        <div className="card-panel-white" style={{ color: '#B91C1C', borderColor: '#FCA5A5', background: '#FEF2F2', padding: 16 }}>{error}</div>
      ) : loading ? (
        <div className="card-panel-white" style={{ textAlign: 'center', padding: 48, color: '#64748B' }}>
          Loading verification runs{selectedRepo ? ` for ${selectedRepo.repositoryFullName}` : ''}…
        </div>
      ) : !selectedRepo ? (
        <div className="card-panel-white" style={{ textAlign: 'center', padding: '56px 24px' }}>
          <FolderGit2 size={38} style={{ color: '#EA580C', margin: '0 auto 14px' }} />
          <h2 style={{ fontSize: 17, fontWeight: 750, color: '#0F172A', marginBottom: 6 }}>
            Select a repository to view verification runs.
          </h2>
          <p style={{ fontSize: 13, color: '#64748B', maxWidth: 440, margin: '0 auto 20px' }}>
            Choose an active connected repository to inspect its pre-flight verification gates and obligation findings.
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
            Verify an engineering plan against an immutable snapshot of this repository to generate your first pre-flight gate report.
          </p>
          <Link href={`/workspace/new-verification${selectedRepo.snapshotId ? `?snapshot_id=${selectedRepo.snapshotId}` : ''}`} className="btn-verify-plan-cta">
            <Plus size={14} />
            Start verification
          </Link>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 14 }}>
          {/* Status Filter Tabs */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', borderBottom: '1px solid #E2E8F0', paddingBottom: 10 }}>
            {filterTabs.map(tab => {
              const count = tab.key === 'ALL' 
                ? runs.length 
                : tab.key === 'HUMAN_WAIT'
                ? runs.filter(r => r.status === 'HUMAN_WAIT' || r.status === 'HUMAN_DECISION_REQUIRED' || r.has_open_human_question).length
                : runs.filter(r => r.status === tab.key).length

              const active = activeFilter === tab.key
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveFilter(tab.key)}
                  style={{
                    background: active ? '#0F172A' : '#F1F5F9',
                    color: active ? '#FFFFFF' : '#475569',
                    border: 'none',
                    borderRadius: 6,
                    padding: '5px 12px',
                    fontSize: 12,
                    fontWeight: 650,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span>{tab.label}</span>
                  <span style={{ 
                    fontSize: 10.5, 
                    padding: '1px 5px', 
                    borderRadius: 10, 
                    background: active ? 'rgba(255,255,255,0.2)' : '#E2E8F0',
                    color: active ? '#FFFFFF' : '#475569',
                  }}>
                    {count}
                  </span>
                </button>
              )
            })}
          </div>

          {filteredRuns.length === 0 ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 36, color: '#64748B' }}>
              No runs match status filter &quot;{activeFilter}&quot;.
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 12 }}>
              {filteredRuns.map(run => {
                const commit = run.commit_sha ? run.commit_sha.slice(0, 7) : undefined
                const ref = run.ref || selectedRepo?.ref || 'main'
                const planTitle = run.plan_title || 'Software change verification'

                return (
                  <article 
                    key={run.id} 
                    className="card-panel-white" 
                    style={{ 
                      padding: 16, 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center', 
                      flexWrap: 'wrap', 
                      gap: 16 
                    }}
                  >
                    <div style={{ display: 'grid', gap: 6, minWidth: 260, flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13, color: '#0F172A' }}>
                          run-{run.id.slice(0, 8)}
                        </span>
                        {getStatusBadge(run.status, run.has_open_human_question)}
                        <span style={{ fontSize: 11.5, color: '#64748B' }}>
                          {new Date(run.created_at).toLocaleString()}
                        </span>
                      </div>

                      <strong 
                        style={{ 
                          fontSize: 14.5, 
                          color: '#0F172A', 
                          lineHeight: 1.35,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                        title={planTitle}
                      >
                        {planTitle}
                      </strong>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 11.5, color: '#64748B', flexWrap: 'wrap' }}>
                        {ref && (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontWeight: 600, color: '#475569' }}>
                            <GitBranch size={11} /> {ref}
                          </span>
                        )}
                        {commit && (
                          <span className="commit-mini-tag">
                            <GitCommit size={10} style={{ marginRight: 2 }} />
                            {commit}
                          </span>
                        )}
                        <span>snap-{run.snapshot_id.slice(0, 7)}</span>
                        <span>·</span>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: '#475569' }}>
                          <FileText size={11} /> <strong>{run.evidence_count ?? 0}</strong> evidence
                        </span>
                        <span>·</span>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: '#475569' }}>
                          <Wrench size={11} /> <strong>{run.tool_execution_count ?? run.tool_call_count ?? 0}</strong> tools
                        </span>
                      </div>
                    </div>

                    <div>
                      <Link 
                        href={`/workspace/runs/${run.id}`} 
                        className="btn-plan-action"
                        style={{ fontSize: 12, padding: '7px 14px' }}
                      >
                        <span>View report</span>
                        <ArrowRight size={12} />
                      </Link>
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

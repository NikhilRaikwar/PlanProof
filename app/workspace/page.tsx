'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import { 
  Activity, 
  ArrowRight, 
  Check,
  CheckCircle2, 
  Clock, 
  ExternalLink, 
  FileText, 
  FolderGit2, 
  GitBranch, 
  GitCommit, 
  HelpCircle, 
  Layers3, 
  LayoutDashboard, 
  Play, 
  Plus, 
  ShieldAlert, 
  ShieldCheck, 
  Sparkles, 
  User 
} from 'lucide-react'
import { api, ApiError, Project, Snapshot, VerificationRun, Session } from '@/lib/api'
import { GithubIcon } from '@/components/repo-context-chip'
import { useWorkspace } from '@/components/workspace-context'

export default function WorkspaceDashboardPage() {
  const { selectedRepo, selectRepository } = useWorkspace()
  const [session, setSession] = useState<Session | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [snapshots, setSnapshots] = useState<Record<string, Snapshot>>({})
  const [recentRuns, setRecentRuns] = useState<VerificationRun[]>([])
  const [engineReady, setEngineReady] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadData = async () => {
    setLoading(true)
    setError('')
    void api.health().then(setEngineReady).catch(() => setEngineReady(false))
    try {
      const [sessionData, projectsData, runsData] = await Promise.all([
        api.session().catch(() => null),
        api.workspaceProjects().catch(() => []),
        api.runs(selectedRepo?.repositoryId).catch(() => [])
      ])

      setSession(sessionData)

      // Filter out E2E test data from normal user view
      const normalProjects = projectsData.filter(p => !p.name.startsWith('e2e-'))
      setProjects(normalProjects)
      setRecentRuns(runsData.slice(0, 5))

      // Load latest snapshot for each project
      const snapshotMap: Record<string, Snapshot> = {}
      await Promise.all(
        normalProjects.map(async (project) => {
          try {
            const projectSnaps = await api.snapshots(project.id)
            if (projectSnaps && projectSnaps.length > 0) {
              snapshotMap[project.id] = projectSnaps[0]
            }
          } catch {
            // Ignore single project snapshot errors
          }
        })
      )
      setSnapshots(snapshotMap)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load workspace dashboard.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [selectedRepo?.repositoryId])

  const humanRequiredRuns = recentRuns.filter(r => 
    r.status === 'HUMAN_WAIT' || r.status === 'HUMAN_DECISION_REQUIRED'
  )

  const readySnapshotsCount = Object.values(snapshots).filter(s => s.status === 'READY').length

  const formatTimeAgo = (dateString: string) => {
    const diff = Math.floor((Date.now() - new Date(dateString).getTime()) / 1000)
    if (diff < 60) return 'Just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  }

  return (
    <div style={{ display: 'grid', gap: 24 }}>
      {/* Top Header Block */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div className="preflight-eyebrow">
            <LayoutDashboard size={13} />
            <span>WORKSPACE DASHBOARD</span>
          </div>
          <h1 className="page-main-title">Verification Dashboard</h1>
          <p className="page-main-desc">
            Connected repositories, snapshot readiness, and recent Plan Gate reports.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Link href="/workspace/repositories" className="btn-secondary-light" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
            <Layers3 size={14} />
            <span>Select repository</span>
          </Link>
          <Link href="/workspace/new-verification" className="btn-header-cta">
            <Plus size={14} strokeWidth={2.5} />
            <span>Verify a plan</span>
          </Link>
        </div>
      </div>

      {error && (
        <div className="card-panel-white" style={{ borderColor: '#FCA5A5', background: '#FEF2F2', color: '#B91C1C', padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{error}</span>
            <button className="btn-plan-action" onClick={() => void loadData()}>Retry</button>
          </div>
        </div>
      )}

      {/* Needs Attention / Human Gate Banner */}
      {humanRequiredRuns.length > 0 && (
        <div className="card-panel-white" style={{ borderColor: '#FDBA74', background: '#FFF7ED', borderLeft: '4px solid #EA580C' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: '#FFEDD5', color: '#EA580C', display: 'grid', placeItems: 'center', flexShrink: 0 }}>
                <ShieldAlert size={20} />
              </div>
              <div>
                <strong style={{ fontSize: 14, color: '#9A3412', display: 'block' }}>
                  {humanRequiredRuns.length} verification {humanRequiredRuns.length === 1 ? 'run requires' : 'runs require'} human authorization
                </strong>
                <span style={{ fontSize: 12, color: '#C2410C' }}>
                  High-risk proof obligations cannot be decided automatically from code evidence alone.
                </span>
              </div>
            </div>
            <Link 
              href={`/workspace/runs/${humanRequiredRuns[0].id}`} 
              className="btn-verify-plan-cta" 
              style={{ fontSize: 12, padding: '6px 14px', textDecoration: 'none' }}
            >
              <span>Review decisions</span>
              <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      )}

      {/* Connected Account & Workspace Status Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        {/* Connected GitHub Account Card */}
        <div className="card-panel-white">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {session?.account_login ? (
                <img 
                  src={`https://github.com/${session.account_login}.png?size=80`}
                  alt={session.account_login}
                  style={{ width: 38, height: 38, borderRadius: 10, objectFit: 'cover' }}
                />
              ) : (
                <div style={{ width: 38, height: 38, borderRadius: 10, background: '#0F172A', color: '#FFF', display: 'grid', placeItems: 'center' }}>
                  <GithubIcon size={20} />
                </div>
              )}
              <div>
                <strong style={{ fontSize: 14, color: '#0F172A', display: 'block' }}>
                  {session?.account_login ? `@${session.account_login}` : 'Connected Account'}
                </strong>
                <span style={{ fontSize: 11.5, color: '#64748B' }}>
                  {session?.installation_id ? `GitHub App #${session.installation_id}` : 'Verified installation'}
                </span>
              </div>
            </div>
            <span className="badge-pill-base badge-verified" style={{ fontSize: 10.5 }}>
              <span className="synced-green-dot" />
              Connected
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, borderTop: '1px solid #F1F5F9', fontSize: 12 }}>
            <span style={{ color: '#64748B' }}>Granted Repositories</span>
            <strong style={{ color: '#0F172A' }}>{projects.length} connected</strong>
          </div>
        </div>

        {/* Snapshot Readiness Metric */}
        <div className="card-panel-white">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
            <div>
              <span style={{ fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', color: '#EA580C', letterSpacing: 0.5 }}>
                SNAPSHOT READINESS
              </span>
              <strong style={{ fontSize: 22, color: '#0F172A', display: 'block', marginTop: 4 }}>
                {readySnapshotsCount} READY
              </strong>
            </div>
            <div style={{ width: 38, height: 38, borderRadius: 10, background: '#FFF1EB', color: '#EA580C', display: 'grid', placeItems: 'center' }}>
              <Layers3 size={19} />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, borderTop: '1px solid #F1F5F9', fontSize: 12 }}>
            <span style={{ color: '#64748B' }}>Immutable Evidence Base</span>
            <Link href="/workspace/repositories" style={{ color: '#EA580C', fontWeight: 600, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              Manage snapshots <ArrowRight size={11} />
            </Link>
          </div>
        </div>

        {/* Verification Engine State */}
        <div className="card-panel-white">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
            <div>
              <span style={{ fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', color: engineReady === false ? '#DC2626' : '#16A34A', letterSpacing: 0.5 }}>
                VERIFICATION ENGINE
              </span>
              <strong style={{ fontSize: 22, color: '#0F172A', display: 'block', marginTop: 4 }}>
                {engineReady === null ? 'Checking…' : engineReady ? 'Operational' : 'Unavailable'}
              </strong>
            </div>
            <div style={{ width: 38, height: 38, borderRadius: 10, background: engineReady === false ? '#FEE2E2' : '#DCFCE7', color: engineReady === false ? '#DC2626' : '#16A34A', display: 'grid', placeItems: 'center' }}>
              <ShieldCheck size={20} />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, borderTop: '1px solid #F1F5F9', fontSize: 12 }}>
            <span style={{ color: '#64748B' }}>Deterministic Gate</span>
            <span style={{ color: '#0F172A', fontWeight: 600 }}>{engineReady === false ? 'Engine Offline' : 'Deterministic Evidence Gate'}</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Connected Repositories & Recent Verification Runs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 20 }}>
        {/* Connected Repositories Column */}
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: 16, fontWeight: 800, color: '#0F172A', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
              <FolderGit2 size={17} color="#EA580C" />
              Connected Repositories
            </h2>
            <Link href="/workspace/repositories" style={{ fontSize: 12.5, fontWeight: 700, color: '#EA580C', textDecoration: 'none' }}>
              View all
            </Link>
          </div>

          {loading ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 36, color: '#64748B' }}>
              Loading repositories…
            </div>
          ) : projects.length === 0 ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 36 }}>
              <FolderGit2 size={32} style={{ color: '#94A3B8', margin: '0 auto 10px' }} />
              <h3 style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 4 }}>No repositories connected yet</h3>
              <p style={{ fontSize: 12, color: '#64748B', maxWidth: 300, margin: '0 auto 16px' }}>
                Grant PlanProof access to your GitHub repositories to start extracting proof obligations.
              </p>
              <Link href="/workspace/repositories" className="btn-verify-plan-cta" style={{ fontSize: 12, padding: '7px 14px', textDecoration: 'none', display: 'inline-flex' }}>
                <Plus size={14} />
                <span>Connect repository</span>
              </Link>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              {projects.map(project => {
                const snapshot = snapshots[project.id]
                const isDemo = project.repository_source_type === 'seeded_fixture'
                const isReady = snapshot?.status === 'READY'
                const isActive = selectedRepo?.repositoryId === project.id

                return (
                  <div key={project.id} className="card-panel-white" style={{ display: 'grid', gap: 10, padding: 16, border: isActive ? '1px solid #EA580C' : undefined }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <strong style={{ fontSize: 13.5, color: '#0F172A', wordBreak: 'break-word' }}>
                            {project.name}
                          </strong>
                          {isActive && (
                            <span className="badge-pill-base badge-verified" style={{ fontSize: 10, padding: '2px 8px' }}>
                              <Check size={11} strokeWidth={2.5} />
                              Active
                            </span>
                          )}
                          {isDemo && (
                            <span style={{ fontSize: 10, fontWeight: 750, background: '#FEF3C7', color: '#D97706', padding: '2px 6px', borderRadius: 4 }}>
                              DEMO FIXTURE
                            </span>
                          )}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4, fontSize: 11.5, color: '#64748B', flexWrap: 'wrap' }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <GitBranch size={12} />
                            {snapshot?.requested_ref || project.requested_ref || 'main'}
                          </span>
                          {snapshot?.resolved_commit_sha && (
                            <span className="commit-mini-tag">
                              <GitCommit size={10} style={{ marginRight: 2 }} />
                              {snapshot.resolved_commit_sha.slice(0, 7)}
                            </span>
                          )}
                        </div>
                      </div>

                      <div>
                        {snapshot ? (
                          <span 
                            className={`badge-pill-base ${
                              isReady ? 'badge-verified' : snapshot.status === 'FAILED' ? 'badge-blocked' : 'badge-queued'
                            }`}
                            style={{ fontSize: 11 }}
                          >
                            <span 
                              className="synced-green-dot" 
                              style={{ 
                                background: isReady ? '#16A34A' : snapshot.status === 'FAILED' ? '#DC2626' : '#F59E0B' 
                              }} 
                            />
                            {snapshot.status}
                          </span>
                        ) : (
                          <span className="badge-pill-base badge-queued" style={{ fontSize: 11 }}>
                            NO SNAPSHOT
                          </span>
                        )}
                      </div>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 8, borderTop: '1px solid #F1F5F9', fontSize: 11.5 }}>
                      <span style={{ color: '#64748B' }}>
                        {snapshot ? `${snapshot.files_indexed ?? 0} files · ${snapshot.symbols_indexed ?? 0} symbols` : 'Awaiting snapshot creation'}
                      </span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {!isActive && (
                          <button
                            type="button"
                            className="btn-secondary-light"
                            style={{ fontSize: 11, padding: '3px 8px' }}
                            onClick={() => selectRepository(project, snapshot)}
                          >
                            Set active
                          </button>
                        )}
                        {isReady ? (
                          <Link 
                            href={`/workspace/new-verification?snapshot_id=${snapshot.id}`}
                            onClick={() => selectRepository(project, snapshot)}
                            style={{ color: '#EA580C', fontWeight: 700, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                          >
                            <span>Verify plan</span>
                            <ArrowRight size={11} />
                          </Link>
                        ) : (
                          <Link 
                            href="/workspace/repositories"
                            style={{ color: '#64748B', fontWeight: 600, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                          >
                            <span>Create snapshot</span>
                            <ArrowRight size={11} />
                          </Link>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Recent Verification Runs Column */}
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: 16, fontWeight: 800, color: '#0F172A', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Activity size={17} color="#EA580C" />
              Recent Verification Runs {selectedRepo ? `· ${selectedRepo.repositoryFullName.split('/').pop()}` : ''}
            </h2>
            <Link href="/workspace/runs" style={{ fontSize: 12.5, fontWeight: 700, color: '#EA580C', textDecoration: 'none' }}>
              View all
            </Link>
          </div>

          {loading ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 36, color: '#64748B' }}>
              Loading recent runs…
            </div>
          ) : recentRuns.length === 0 ? (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: 36 }}>
              <Activity size={32} style={{ color: '#94A3B8', margin: '0 auto 10px' }} />
              <h3 style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 4 }}>No verification runs yet</h3>
              <p style={{ fontSize: 12, color: '#64748B', maxWidth: 300, margin: '0 auto 16px' }}>
                Verify your first engineering plan against a connected repository snapshot.
              </p>
              <Link href="/workspace/new-verification" className="btn-verify-plan-cta" style={{ fontSize: 12, padding: '7px 14px', textDecoration: 'none', display: 'inline-flex' }}>
                <Plus size={14} />
                <span>Verify a plan</span>
              </Link>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              {recentRuns.map(run => {
                const project = projects.find(p => p.id === run.project_id)
                const isBlocked = run.status === 'BLOCKED'
                const isVerified = run.status === 'COMPLETE' || run.status === 'VERIFIED'
                const isHuman = run.status === 'HUMAN_WAIT' || run.status === 'HUMAN_DECISION_REQUIRED'

                return (
                  <Link 
                    key={run.id} 
                    href={`/workspace/runs/${run.id}`}
                    style={{ textDecoration: 'none' }}
                  >
                    <div className="card-panel-white" style={{ display: 'grid', gap: 8, padding: 14, transition: 'all 0.15s ease', cursor: 'pointer' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ fontSize: 12, fontWeight: 700, color: '#0F172A' }}>
                            {project?.name || 'Repository Verification'}
                          </span>
                          <span className="commit-mini-tag">
                            Run {run.id.slice(0, 8)}
                          </span>
                        </div>

                        <span 
                          className={`badge-pill-base ${
                            isVerified ? 'badge-verified' : isBlocked ? 'badge-blocked' : isHuman ? 'badge-human' : run.status === 'INCONCLUSIVE' ? 'badge-inconclusive' : 'badge-queued'
                          }`}
                          style={{ fontSize: 10.5 }}
                        >
                          {isHuman ? 'HUMAN DECISION REQUIRED' : run.status === 'INCONCLUSIVE' ? 'INCONCLUSIVE' : run.status.replaceAll('_', ' ')}
                        </span>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: '#64748B' }}>
                        <span>
                          {run.tool_call_count} tool {run.tool_call_count === 1 ? 'call' : 'calls'} · {run.model_call_count} model {run.model_call_count === 1 ? 'call' : 'calls'}
                        </span>
                        <span>{formatTimeAgo(run.created_at)}</span>
                      </div>
                    </div>
                  </Link>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

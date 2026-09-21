'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import { 
  ArrowRight, 
  Check, 
  ChevronDown, 
  ExternalLink, 
  FolderGit2, 
  GitBranch, 
  GitCommit, 
  Layers3, 
  Loader2, 
  Lock, 
  Plus, 
  RefreshCw, 
  Sparkles 
} from 'lucide-react'
import { api, ApiError, GitHubRef, GitHubRepository, Project, Snapshot } from '@/lib/api'
import { GithubIcon } from '@/components/repo-context-chip'

type Entry = { project: Project; snapshot?: Snapshot }

export default function RepositoriesPage() {
  const [items, setItems] = useState<Entry[]>([])
  const [githubRepos, setGithubRepos] = useState<GitHubRepository[]>([])
  const [repoRefs, setRepoRefs] = useState<Record<number, GitHubRef[]>>({})
  const [selectedRefs, setSelectedRefs] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(true)
  const [creatingForRepo, setCreatingForRepo] = useState<number | null>(null)
  const [creatingDemo, setCreatingDemo] = useState(false)
  const [error, setError] = useState('')
  const [manualOpen, setManualOpen] = useState(false)
  const [manualType, setManualType] = useState<'public_github' | 'seeded_fixture'>('public_github')
  const [manualUrl, setManualUrl] = useState('')
  const [manualRef, setManualRef] = useState('main')
  const [manualName, setManualName] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [projects, ghRepos] = await Promise.all([
        api.workspaceProjects().catch(() => api.projects().catch(() => [])),
        api.githubRepositories().catch(() => [])
      ])

      const rows = await Promise.all(
        projects.map(async project => {
          try {
            const snaps = await api.snapshots(project.id)
            return { project, snapshot: snaps[0] }
          } catch {
            return { project, snapshot: undefined }
          }
        })
      )
      setItems(rows)
      setGithubRepos(ghRepos)

      // Initialize default branch selections for GitHub repos
      const refMap: Record<number, string> = {}
      ghRepos.forEach(r => {
        refMap[r.id] = r.default_branch || 'main'
      })
      setSelectedRefs(refMap)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load repositories.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  // Poll while any snapshot is actively indexing or queued
  useEffect(() => {
    const hasActiveSnapshot = items.some(
      ({ snapshot }) => snapshot && !['READY', 'FAILED', 'UNSUPPORTED'].includes(snapshot.status)
    )
    if (!hasActiveSnapshot) return
    const timeout = window.setTimeout(() => { void load() }, 2_000)
    return () => window.clearTimeout(timeout)
  }, [items])

  const loadRefsForRepo = async (repoId: number) => {
    if (repoRefs[repoId]) return
    try {
      const refs = await api.githubRefs(repoId)
      setRepoRefs(prev => ({ ...prev, [repoId]: refs }))
    } catch {
      // Ignore refs load error
    }
  }

  const handleCreateSnapshot = async (repo: GitHubRepository) => {
    setError('')
    setCreatingForRepo(repo.id)
    try {
      const branch = selectedRefs[repo.id] || repo.default_branch || 'main'
      await api.createConnectedSnapshot(repo.id, branch)
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `Could not create snapshot for ${repo.full_name}`)
    } finally {
      setCreatingForRepo(null)
    }
  }

  const handleCreateDemoSnapshot = async () => {
    setError('')
    setCreatingDemo(true)
    try {
      await api.createDemoSnapshot()
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create demo snapshot.')
    } finally {
      setCreatingDemo(false)
    }
  }

  const handleManualAdd = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    try {
      const project = await api.createProject(
        manualType === 'public_github'
          ? {
              name: manualName || manualUrl,
              owner_id: 'local-session',
              repository_source: { type: manualType, repository_url: manualUrl, requested_ref: manualRef || undefined }
            }
          : {
              name: manualName || 'Partial Refund Demo',
              owner_id: 'local-session',
              repository_source: { type: manualType, fixture_id: 'partial-refunds-v1' }
            }
      )
      await api.createSnapshot(project.id)
      setManualOpen(false)
      setManualUrl('')
      setManualName('')
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not add repository.')
    }
  }

  return (
    <div style={{ display: 'grid', gap: 24 }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div className="preflight-eyebrow">
            <Layers3 size={13} />
            <span>CONNECTED REPOSITORIES & SNAPSHOTS</span>
          </div>
          <h1 className="page-main-title">Repository Management</h1>
          <p className="page-main-desc">
            Immutable commit snapshots serve as the authoritative evidence source for plan verification.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button 
            type="button" 
            className="btn-secondary-light"
            data-testid="index-demo-fixture"
            disabled={creatingDemo || loading}
            onClick={() => void handleCreateDemoSnapshot()}
          >
            <Sparkles size={13} className={creatingDemo ? 'animate-spin' : ''} />
            <span>{creatingDemo ? 'Indexing demo…' : 'Index demo fixture'}</span>
          </button>

          <button 
            type="button" 
            className="btn-secondary-light"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>

          <button 
            type="button" 
            className="btn-verify-plan-cta"
            onClick={() => setManualOpen(!manualOpen)}
          >
            <Plus size={14} />
            <span>{manualOpen ? 'Close manual add' : 'Add public repo / demo'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="card-panel-white" style={{ borderColor: '#FCA5A5', background: '#FEF2F2', color: '#B91C1C', padding: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{error}</span>
            <button className="btn-plan-action" onClick={() => void load()}>Retry</button>
          </div>
        </div>
      )}

      {/* Manual / Public URL Form (Optional fallback) */}
      {manualOpen && (
        <form onSubmit={handleManualAdd} className="card-panel-white" style={{ display: 'grid', gap: 14 }}>
          <div style={{ borderBottom: '1px solid #F1F5F9', paddingBottom: 10 }}>
            <strong style={{ fontSize: 14, color: '#0F172A' }}>Manual Repository / Demo Ingestion</strong>
            <p style={{ fontSize: 12, color: '#64748B', margin: '2px 0 0' }}>
              Index a public Git repository or the built-in partial refund demo fixture.
            </p>
          </div>

          <div className="form-field-block">
            <label className="form-field-label" htmlFor="manual-source-type">Source type</label>
            <select 
              id="manual-source-type" 
              className="custom-select-box"
              value={manualType} 
              onChange={e => setManualType(e.target.value as typeof manualType)}
            >
              <option value="public_github">Public GitHub repository</option>
              <option value="seeded_fixture">Demo fixture — partial refunds</option>
            </select>
          </div>

          {manualType === 'public_github' && (
            <>
              <div className="form-field-block">
                <label className="form-field-label" htmlFor="manual-url">Public GitHub URL</label>
                <input 
                  id="manual-url" 
                  required 
                  className="custom-text-input" 
                  value={manualUrl} 
                  onChange={e => setManualUrl(e.target.value)} 
                  placeholder="https://github.com/owner/repository"
                />
              </div>
              <div className="form-field-block">
                <label className="form-field-label" htmlFor="manual-ref">Requested ref / branch</label>
                <input 
                  id="manual-ref" 
                  className="custom-text-input" 
                  value={manualRef} 
                  onChange={e => setManualRef(e.target.value)} 
                  placeholder="main"
                />
              </div>
            </>
          )}

          <div className="form-field-block">
            <label className="form-field-label" htmlFor="manual-name">Display name (optional)</label>
            <input 
              id="manual-name" 
              className="custom-text-input" 
              value={manualName} 
              onChange={e => setManualName(e.target.value)} 
              placeholder="e.g. My Service"
            />
          </div>

          <div>
            <button className="btn-verify-plan-cta" type="submit">
              <GitBranch size={14} />
              <span>Create and index snapshot</span>
            </button>
          </div>
        </form>
      )}

      {/* GitHub App Granted Repositories Section */}
      {githubRepos.length > 0 && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <GithubIcon size={16} />
              <strong style={{ fontSize: 14.5, color: '#0F172A' }}>
                GitHub App Repositories ({githubRepos.length})
              </strong>
            </div>
            <span style={{ fontSize: 11.5, color: '#64748B' }}>
              Select a branch to index an immutable snapshot
            </span>
          </div>

          <div style={{ display: 'grid', gap: 10 }}>
            {githubRepos.map(repo => {
              const matchingItem = items.find(
                item => item.project.github_repository_id === repo.id || item.project.name === repo.full_name
              )
              const currentSnap = matchingItem?.snapshot
              const isCreating = creatingForRepo === repo.id
              const branches = repoRefs[repo.id]

              return (
                <div key={repo.id} className="card-panel-white" style={{ display: 'grid', gap: 12, padding: 18 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <strong style={{ fontSize: 14, color: '#0F172A' }}>{repo.full_name}</strong>
                        {repo.private ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, fontWeight: 700, background: '#F1F5F9', color: '#475569', padding: '2px 6px', borderRadius: 4 }}>
                            <Lock size={10} /> Private
                          </span>
                        ) : (
                          <span style={{ fontSize: 10, fontWeight: 700, background: '#ECFDF5', color: '#059669', padding: '2px 6px', borderRadius: 4 }}>
                            Public
                          </span>
                        )}
                      </div>
                      <span style={{ fontSize: 11.5, color: '#64748B', display: 'block', marginTop: 2 }}>
                        Default branch: <code>{repo.default_branch || 'main'}</code>
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      {/* Branch selector */}
                      <div style={{ minWidth: 140 }}>
                        <select 
                          className="custom-select-box"
                          style={{ padding: '6px 10px', fontSize: 12 }}
                          value={selectedRefs[repo.id] || repo.default_branch || 'main'}
                          onFocus={() => void loadRefsForRepo(repo.id)}
                          onChange={e => setSelectedRefs(prev => ({ ...prev, [repo.id]: e.target.value }))}
                        >
                          {branches ? (
                            branches.map(b => (
                              <option key={b.name} value={b.name}>{b.name} ({b.commit_sha.slice(0, 7)})</option>
                            ))
                          ) : (
                            <option value={repo.default_branch || 'main'}>{repo.default_branch || 'main'}</option>
                          )}
                        </select>
                      </div>

                      <button
                        type="button"
                        className="btn-verify-plan-cta"
                        style={{ fontSize: 12, padding: '7px 14px' }}
                        disabled={isCreating}
                        onClick={() => void handleCreateSnapshot(repo)}
                      >
                        {isCreating ? (
                          <>
                            <Loader2 size={13} className="animate-spin" />
                            <span>Indexing…</span>
                          </>
                        ) : (
                          <>
                            <GitBranch size={13} />
                            <span>Index snapshot</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {currentSnap && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 10, borderTop: '1px solid #F1F5F9', fontSize: 11.5, flexWrap: 'wrap', gap: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span className="badge-pill-base badge-verified">
                          <span className="synced-green-dot" />
                          {currentSnap.status}
                        </span>
                        {currentSnap.resolved_commit_sha && (
                          <span className="commit-mini-tag">
                            <GitCommit size={10} style={{ marginRight: 2 }} />
                            {currentSnap.resolved_commit_sha.slice(0, 7)}
                          </span>
                        )}
                        <span style={{ color: '#64748B' }}>
                          {currentSnap.files_indexed ?? 0} files · {currentSnap.symbols_indexed ?? 0} symbols
                        </span>
                      </div>

                      {currentSnap.status === 'READY' && (
                        <Link 
                          href="/workspace/new-verification"
                          style={{ color: '#EA580C', fontWeight: 700, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                        >
                          <span>Verify a plan with this snapshot</span>
                          <ArrowRight size={11} />
                        </Link>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Indexed Snapshots & Projects List */}
      <div style={{ display: 'grid', gap: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <strong style={{ fontSize: 14.5, color: '#0F172A' }}>
            Indexed Snapshots ({items.length})
          </strong>
          <span style={{ fontSize: 11.5, color: '#64748B' }}>
            Resolved immutable snapshots ready for pre-flight verification
          </span>
        </div>

        {loading ? (
          <div className="card-panel-white" style={{ textAlign: 'center', padding: 48, color: '#64748B' }}>
            Loading repository snapshots…
          </div>
        ) : items.length === 0 ? (
          <div className="card-panel-white" style={{ textAlign: 'center', padding: 56 }}>
            <Layers3 size={36} style={{ color: '#EA580C', margin: '0 auto 12px' }} />
            <h2 style={{ fontSize: 16, fontWeight: 750, color: '#0F172A', marginBottom: 4 }}>No repositories connected</h2>
            <p style={{ fontSize: 13, color: '#64748B', maxWidth: 360, margin: '0 auto 20px' }}>
              Index a repository snapshot from your GitHub App installation or try the built-in demo fixture.
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: 12 }}>
              <button 
                type="button" 
                className="btn-verify-plan-cta"
                disabled={creatingDemo}
                onClick={() => void handleCreateDemoSnapshot()}
              >
                <Sparkles size={14} />
                <span>{creatingDemo ? 'Indexing Demo…' : 'Try Demo Fixture (Partial Refunds)'}</span>
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 12 }}>
            {items.map(({ project, snapshot }) => {
              const isDemo = project.repository_source_type === 'seeded_fixture'
              const isReady = snapshot?.status === 'READY'

              return (
                <div key={project.id} className="card-panel-white" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <strong style={{ fontSize: 14, color: '#0F172A' }}>{project.name}</strong>
                      {isDemo && (
                        <span style={{ fontSize: 10, fontWeight: 750, background: '#FEF3C7', color: '#D97706', padding: '2px 6px', borderRadius: 4 }}>
                          Demo fixture
                        </span>
                      )}
                    </div>
                    <p style={{ fontSize: 12, color: '#64748B', margin: '3px 0 6px' }}>
                      {isDemo ? 'Built-in partial refund scenario' : project.repository_url}
                    </p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5 }}>
                      <span className="commit-mini-tag">
                        <GitCommit size={10} style={{ marginRight: 2 }} />
                        {snapshot?.resolved_commit_sha?.slice(0, 7) || 'Resolving…'}
                      </span>
                      <span style={{ color: '#64748B', display: 'flex', alignItems: 'center', gap: 3 }}>
                        <GitBranch size={11} /> {snapshot?.requested_ref || project.requested_ref || 'main'}
                      </span>
                    </div>
                  </div>

                  <div style={{ textAlign: 'right', display: 'grid', gap: 4 }}>
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
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

                    <p style={{ fontSize: 11.5, color: '#64748B', margin: 0 }}>
                      {snapshot?.files_indexed ?? 0} files · {snapshot?.symbols_indexed ?? 0} symbols
                    </p>

                    {isReady && (
                      <div style={{ marginTop: 2 }}>
                        <Link 
                          href="/workspace/new-verification"
                          className="btn-plan-action"
                          style={{ fontSize: 11.5, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                        >
                          <span>Verify a plan</span>
                          <ArrowRight size={10} />
                        </Link>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Demo Fixture Quick Card */}
      <div className="card-panel-subtle" style={{ background: '#FFFBF5', borderColor: '#FED7AA', padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Sparkles size={15} color="#EA580C" />
              <strong style={{ fontSize: 13.5, color: '#9A3412' }}>Partial Refund Demo Fixture</strong>
            </div>
            <p style={{ fontSize: 12, color: '#C2410C', margin: '3px 0 0' }}>
              Want to see PlanProof in action without connecting a private repository? Index our partial refund demo repo.
            </p>
          </div>

          <button
            type="button"
            className="btn-secondary-light"
            style={{ fontSize: 12, background: '#FFFFFF' }}
            disabled={creatingDemo}
            onClick={() => void handleCreateDemoSnapshot()}
          >
            {creatingDemo ? 'Indexing…' : 'Create Demo Snapshot'}
          </button>
        </div>
      </div>
    </div>
  )
}

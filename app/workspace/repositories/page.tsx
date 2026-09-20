'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import {
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  Database,
  ExternalLink,
  GitBranch,
  Layers3,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Zap,
} from 'lucide-react'
import { GithubIcon } from '@/components/repo-context-chip'

interface RepoItem {
  id: string
  name: string
  owner: string
  branch: string
  commit: string
  isDefault: boolean
  status: 'ACTIVE' | 'INDEXING'
  syncedTime: string
  filesCount: number
  symbolsCount: number
  astStatus: string
}

const reposList: RepoItem[] = [
  {
    id: 'repo-1',
    name: 'planproof',
    owner: 'nikhilraikwar',
    branch: 'main',
    commit: '8f3c1a2',
    isDefault: true,
    status: 'ACTIVE',
    syncedTime: 'Just now',
    filesCount: 142,
    symbolsCount: 1840,
    astStatus: 'Fresh index'
  },
  {
    id: 'repo-2',
    name: 'payments-service',
    owner: 'nikhilraikwar',
    branch: 'main',
    commit: 'a1d9e4f',
    isDefault: false,
    status: 'ACTIVE',
    syncedTime: '2 hours ago',
    filesCount: 88,
    symbolsCount: 960,
    astStatus: 'Fresh index'
  },
  {
    id: 'repo-3',
    name: 'billing-platform',
    owner: 'nikhilraikwar',
    branch: 'main',
    commit: 'c7e2b91',
    isDefault: false,
    status: 'ACTIVE',
    syncedTime: '1 day ago',
    filesCount: 215,
    symbolsCount: 3420,
    astStatus: 'Fresh index'
  }
]

export default function RepositoriesPage() {
  const [syncingRepoId, setSyncingRepoId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const handleSync = (id: string) => {
    setSyncingRepoId(id)
    setTimeout(() => {
      setSyncingRepoId(null)
    }, 1200)
  }

  const filteredRepos = reposList.filter(r => 
    r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    r.owner.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
        <div>
          <div className="preflight-eyebrow">
            <Layers3 size={13} />
            <span>REPOSITORIES</span>
          </div>
          <h1 className="page-main-title">Connected repositories</h1>
          <p className="page-main-desc" style={{ margin: 0 }}>
            Manage connected GitHub repositories, inspect indexing status, and sync latest commits for plan verification.
          </p>
        </div>

        <button 
          className="btn-verify-plan-cta"
          style={{ padding: '8px 16px', fontSize: 12.5 }}
          onClick={() => alert('Connect repository modal: PlanProof handles GitHub OAuth and token indexing automatically.')}
        >
          <Plus size={15} strokeWidth={2.5} />
          <span>Connect repository</span>
        </button>
      </div>

      {/* Two Column Grid */}
      <div className="dashboard-two-col-grid" style={{ gridTemplateColumns: '1.9fr 1.1fr', gap: 20 }}>
        {/* Left Column: Repositories List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Search Bar */}
          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94A3B8' }} />
            <input 
              type="text"
              placeholder="Search repositories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="custom-text-input"
              style={{ paddingLeft: 34, height: 38, fontSize: 12.5 }}
            />
          </div>

          {/* Cards List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {filteredRepos.map((repo) => {
              const isSyncing = syncingRepoId === repo.id

              return (
                <div 
                  key={repo.id}
                  className="card-panel-white"
                  style={{
                    padding: '18px 20px',
                    border: repo.isDefault ? '1.5px solid #EA580C' : '1px solid #E2E8F0',
                    transition: 'all 0.15s ease'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{
                        width: 36,
                        height: 36,
                        borderRadius: 8,
                        background: '#0F172A',
                        color: '#FFFFFF',
                        display: 'grid',
                        placeItems: 'center',
                        flexShrink: 0
                      }}>
                        <GithubIcon size={18} />
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <strong style={{ fontSize: 14, fontWeight: 800, color: '#0F172A' }}>
                            {repo.owner} / {repo.name}
                          </strong>
                          {repo.isDefault && (
                            <span style={{
                              fontSize: 9.5,
                              fontWeight: 850,
                              padding: '2px 6px',
                              borderRadius: 4,
                              background: '#FFF1EB',
                              color: '#EA580C',
                              border: '1px solid #FFD9CA',
                              letterSpacing: '0.4px'
                            }}>
                              DEFAULT
                            </span>
                          )}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: '#64748B', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}><GitBranch size={11} /> {repo.branch}</span>
                          <span>•</span>
                          <span className="commit-mini-tag">{repo.commit}</span>
                          <span>•</span>
                          <span>{repo.filesCount} files</span>
                          <span>•</span>
                          <span>{repo.symbolsCount} symbols</span>
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <button
                        onClick={() => handleSync(repo.id)}
                        className="btn-plan-action"
                        style={{ padding: '6px 10px', fontSize: 11 }}
                        disabled={isSyncing}
                        title="Sync latest AST snapshot"
                      >
                        <RefreshCw size={12} className={isSyncing ? 'animate-spin' : ''} />
                        <span>{isSyncing ? 'Syncing...' : 'Sync'}</span>
                      </button>

                      <Link
                        href="/workspace/new-verification"
                        className="btn-verify-plan-cta"
                        style={{ padding: '6px 12px', fontSize: 11.5, textDecoration: 'none' }}
                      >
                        <span>Verify Plan</span>
                        <ArrowRight size={12} />
                      </Link>
                    </div>
                  </div>

                  {/* Bottom Metadata Badges */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    paddingTop: 10,
                    borderTop: '1px solid #F1F5F9',
                    fontSize: 11,
                    color: '#64748B'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <span className="synced-green-dot" />
                        <strong style={{ color: '#0F172A' }}>AST Ready:</strong> {repo.astStatus}
                      </span>
                      <span>Synced: {repo.syncedTime}</span>
                    </div>

                    <span style={{ fontSize: 10.5, color: '#94A3B8', fontFamily: 'var(--font-mono)' }}>
                      Snapshot: Pinned ({repo.commit})
                    </span>
                  </div>
                </div>
              )
            })}
            {filteredRepos.length === 0 && (
              <div className="card-panel-white" style={{ textAlign: 'center', padding: '50px 20px' }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: '#FFF1EB', color: '#EA580C', display: 'grid', placeItems: 'center', margin: '0 auto 12px' }}>
                  <Layers3 size={22} />
                </div>
                <h3 style={{ fontSize: 16, fontWeight: 800, color: '#0F172A', margin: '0 0 4px' }}>No repositories connected</h3>
                <p style={{ fontSize: 12.5, color: '#64748B', maxWidth: 360, margin: '0 auto 16px' }}>
                  Connect GitHub to start verifying plans against real repository code and contracts.
                </p>
                <button
                  onClick={() => alert('Connect repository: GitHub authorization prompt')}
                  className="btn-verify-plan-cta"
                  style={{ padding: '7px 16px', fontSize: 12 }}
                >
                  <Plus size={14} />
                  <span>Connect repository</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: How repositories are used Info Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="card-panel-white" style={{ padding: 20 }}>
            <h3 className="card-heading-compact" style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 14 }}>
              <BookOpen size={16} style={{ color: '#EA580C' }} />
              <span>How repositories are used</span>
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <div style={{ width: 28, height: 28, borderRadius: 6, background: '#FFF7ED', color: '#EA580C', display: 'grid', placeItems: 'center', flexShrink: 0, marginTop: 2 }}>
                  <ShieldCheck size={15} />
                </div>
                <div>
                  <strong style={{ fontSize: 12.5, color: '#0F172A', display: 'block' }}>Read-only AST Analysis</strong>
                  <p style={{ fontSize: 11.5, color: '#64748B', margin: '2px 0 0', lineHeight: 1.4 }}>
                    PlanProof parses TypeScript, Python, Go, and SQL symbols without executing code or mutating files.
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <div style={{ width: 28, height: 28, borderRadius: 6, background: '#ECFDF5', color: '#059669', display: 'grid', placeItems: 'center', flexShrink: 0, marginTop: 2 }}>
                  <CheckCircle2 size={15} />
                </div>
                <div>
                  <strong style={{ fontSize: 12.5, color: '#0F172A', display: 'block' }}>Pinned Commit Snapshots</strong>
                  <p style={{ fontSize: 11.5, color: '#64748B', margin: '2px 0 0', lineHeight: 1.4 }}>
                    Every verification run binds to an immutable commit hash for reliable, reproducible gate reports.
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <div style={{ width: 28, height: 28, borderRadius: 6, background: '#EFF6FF', color: '#2563EB', display: 'grid', placeItems: 'center', flexShrink: 0, marginTop: 2 }}>
                  <Zap size={15} />
                </div>
                <div>
                  <strong style={{ fontSize: 12.5, color: '#0F172A', display: 'block' }}>Cross-File Dependency Call-graphs</strong>
                  <p style={{ fontSize: 11.5, color: '#64748B', margin: '2px 0 0', lineHeight: 1.4 }}>
                    Maps caller-callee chains across services to verify that plan changes won't cause ripple effects.
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <div style={{ width: 28, height: 28, borderRadius: 6, background: '#FAF5FF', color: '#9333EA', display: 'grid', placeItems: 'center', flexShrink: 0, marginTop: 2 }}>
                  <Database size={15} />
                </div>
                <div>
                  <strong style={{ fontSize: 12.5, color: '#0F172A', display: 'block' }}>Contract & Schema Validation</strong>
                  <p style={{ fontSize: 11.5, color: '#64748B', margin: '2px 0 0', lineHeight: 1.4 }}>
                    Probes OpenAPI endpoints, DDL models, and migration constraints for contradiction detection.
                  </p>
                </div>
              </div>
            </div>

            <div style={{
              marginTop: 18,
              padding: 12,
              background: '#FFF7ED',
              border: '1px solid #FFD9CA',
              borderRadius: 8,
              fontSize: 11.5,
              color: '#9A3412',
              lineHeight: 1.4
            }}>
              <strong>Need to add another repository?</strong>
              <div style={{ marginTop: 2 }}>
                Connect GitHub organizations or specific repositories with read-only repository permissions.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import { GitBranch } from 'lucide-react'
import { api, Project, Snapshot } from '@/lib/api'

// Custom GitHub SVG Icon
export function GithubIcon({ size = 14, className = "" }: { size?: number; className?: string }) {
  return (
    <svg 
      width={size} 
      height={size} 
      className={className} 
      viewBox="0 0 24 24" 
      fill="currentColor"
      style={{ width: `${size}px`, height: `${size}px`, minWidth: `${size}px`, minHeight: `${size}px`, flexShrink: 0 }}
    >
      <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  )
}

export interface RepoContextChipProps {
  repo?: string
  branch?: string
  commit?: string
  syncedText?: string
}

export function RepoContextChip({
  repo,
  branch,
  commit,
  syncedText,
}: RepoContextChipProps) {
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const [activeSnapshot, setActiveSnapshot] = useState<Snapshot | null>(null)

  useEffect(() => {
    if (repo) return
    void (async () => {
      try {
        const projects = await api.workspaceProjects()
        const userProjects = projects.filter(p => !p.name.startsWith('e2e-'))
        if (userProjects.length > 0) {
          const first = userProjects[0]
          setActiveProject(first)
          const snapshots = await api.snapshots(first.id)
          if (snapshots.length > 0) {
            setActiveSnapshot(snapshots[0])
          }
        }
      } catch {
        // Leave neutral state
      }
    })()
  }, [repo])

  const displayRepo = repo || activeProject?.name || 'No repository selected'
  const displayBranch = branch || activeSnapshot?.requested_ref || activeProject?.requested_ref
  const displayCommit = commit || (activeSnapshot?.resolved_commit_sha ? activeSnapshot.resolved_commit_sha.slice(0, 7) : undefined)
  const displaySynced = syncedText || (activeSnapshot ? (activeSnapshot.status === 'READY' ? 'Snapshot READY' : activeSnapshot.status) : 'Select repository')

  return (
    <Link href="/workspace/repositories" style={{ textDecoration: 'none' }}>
      <div className="topbar-repo-badge" style={{ cursor: 'pointer' }}>
        <GithubIcon size={14} />
        <span style={{ fontWeight: 750, color: '#0F172A', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {displayRepo}
        </span>
        {displayBranch && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'var(--font-mono)', fontSize: 11, color: '#64748B' }}>
            <GitBranch size={12} /> {displayBranch}
          </span>
        )}
        {displayCommit && <span className="repo-commit-pill">{displayCommit}</span>}
        <span className="repo-synced-status">
          <span 
            className="synced-green-dot" 
            style={{ 
              background: activeSnapshot?.status === 'READY' ? '#16A34A' : activeSnapshot?.status === 'FAILED' ? '#DC2626' : activeSnapshot ? '#F59E0B' : '#94A3B8' 
            }} 
          />
          {displaySynced}
        </span>
      </div>
    </Link>
  )
}

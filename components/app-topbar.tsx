'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Menu } from 'lucide-react'
import { RepoContextChip } from './repo-context-chip'

export interface AppTopbarProps {
  onToggleMobile?: () => void
}

export function AppTopbar({ onToggleMobile }: AppTopbarProps) {
  const pathname = usePathname()

  const getBreadcrumbTitle = () => {
    if (pathname === '/workspace/new-verification' || pathname === '/workspace') return 'New verification'
    if (pathname.startsWith('/workspace/runs/')) return 'Run report'
    if (pathname === '/workspace/runs') return 'Runs'
    if (pathname === '/workspace/repositories') return 'Repositories'
    if (pathname === '/workspace/evidence') return 'Evidence'
    if (pathname === '/workspace/tool-traces') return 'Tool traces'
    if (pathname === '/workspace/evaluations') return 'Evaluations'
    return 'Workspace'
  }

  return (
    <header className="app-topbar">
      <div className="topbar-breadcrumbs-row">
        {onToggleMobile && (
          <button 
            onClick={onToggleMobile}
            className="mobile-nav-toggle"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, display: 'none' }}
            aria-label="Toggle navigation menu"
          >
            <Menu size={18} />
          </button>
        )}
        <Link href="/workspace/new-verification" className="breadcrumb-link-muted">Workspace</Link>
        <span className="breadcrumb-sep-slash">/</span>
        <strong className="breadcrumb-bold-active">
          {getBreadcrumbTitle()}
        </strong>
      </div>

      <div className="topbar-right-box">
        {/* Connected Repo Chip */}
        <RepoContextChip />
      </div>
    </header>
  )
}

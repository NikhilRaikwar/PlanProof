'use client'

import React, { useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Activity,
  BookOpen,
  ChevronDown,
  ExternalLink,
  FileText,
  Layers3,
  LogOut,
  Plus,
  Terminal,
  User,
} from 'lucide-react'

export interface AppSidebarProps {
  mobileOpen?: boolean
  onCloseMobile?: () => void
}

export function AppSidebar({ mobileOpen = false, onCloseMobile }: AppSidebarProps) {
  const pathname = usePathname()
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  const isNewVerificationActive = pathname === '/workspace/new-verification' || pathname === '/workspace'
  const isRunsActive = pathname.startsWith('/workspace/runs')
  const isRepositoriesActive = pathname === '/workspace/repositories'
  const isEvidenceActive = pathname === '/workspace/evidence'
  const isTracesActive = pathname === '/workspace/tool-traces'
  const isEvaluationsActive = pathname === '/workspace/evaluations'

  const handleNavClick = () => {
    if (onCloseMobile) onCloseMobile()
  }

  return (
    <aside className={`app-sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
      <div>
        {/* Logo Brand Lockup */}
        <div className="sidebar-brand-box">
          <Link href="/" className="brand-link-wrap">
            <div className="nav-logo-box" style={{ width: 26, height: 26 }}>
              <Image src="/logo.png" alt="PlanProof" width={24} height={24} priority />
            </div>
            <span className="brand-name-text">PlanProof</span>
          </Link>
          <span className="brand-beta-pill">
            BETA
          </span>
        </div>

        {/* Nav Links Sections */}
        <div className="sidebar-nav-scroll">
          {/* BUILD Section */}
          <div>
            <div className="sidebar-section-title">
              BUILD
            </div>
            <div className="sidebar-btn-list">
              <Link 
                href="/workspace/new-verification"
                onClick={handleNavClick}
                className={`sidebar-nav-item-btn ${isNewVerificationActive ? 'active' : ''}`}
                style={{ textDecoration: 'none' }}
              >
                <div className="nav-item-left-content">
                  <Plus size={15} strokeWidth={2.6} />
                  <span>New verification</span>
                </div>
              </Link>

              <Link 
                href="/workspace/runs"
                onClick={handleNavClick}
                className={`sidebar-nav-item-btn ${isRunsActive ? 'active' : ''}`}
                style={{ textDecoration: 'none' }}
              >
                <div className="nav-item-left-content">
                  <Activity size={15} />
                  <span>Runs</span>
                </div>
                <span className="nav-item-count-badge">12</span>
              </Link>

              <Link 
                href="/workspace/repositories"
                onClick={handleNavClick}
                className={`sidebar-nav-item-btn ${isRepositoriesActive ? 'active' : ''}`}
                style={{ textDecoration: 'none' }}
              >
                <div className="nav-item-left-content">
                  <Layers3 size={15} />
                  <span>Repositories</span>
                </div>
                <span className="nav-item-count-badge">3</span>
              </Link>
            </div>
          </div>

          {/* VERIFY Section */}
          <div>
            <div className="sidebar-section-title">
              VERIFY
            </div>
            <div className="sidebar-btn-list">
              <Link 
                href="/workspace/evidence"
                onClick={handleNavClick}
                className={`sidebar-nav-item-btn ${isEvidenceActive ? 'active' : ''}`}
                style={{ textDecoration: 'none' }}
              >
                <div className="nav-item-left-content">
                  <FileText size={15} />
                  <span>Evidence</span>
                </div>
              </Link>

              <Link 
                href="/workspace/tool-traces"
                onClick={handleNavClick}
                className={`sidebar-nav-item-btn ${isTracesActive ? 'active' : ''}`}
                style={{ textDecoration: 'none' }}
              >
                <div className="nav-item-left-content">
                  <Terminal size={15} />
                  <span>Tool traces</span>
                </div>
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Sidebar Footer: Engine Status Banner + Workspace Profile Card at Bottom */}
      <div className="sidebar-bottom-pill-box" style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '12px 14px' }}>
        <div className="engine-status-banner" style={{ padding: '6px 10px', fontSize: '10.5px' }}>
          <span className="engine-status-dot" />
          <span>Verification engine operational</span>
        </div>

        {/* User Workspace Profile Card with Upward Dropdown at Bottom */}
        <div style={{ position: 'relative' }}>
          <div 
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="sidebar-profile-card"
            style={{ margin: 0 }}
            role="button"
            tabIndex={0}
          >
            <div className="profile-card-left">
              <div className="profile-avatar-square">
                <User size={15} strokeWidth={2.5} />
              </div>
              <div className="profile-info-stack">
                <strong className="profile-user-name">Nikhil Raikwar</strong>
                <span className="profile-workspace-label">Personal workspace</span>
              </div>
            </div>
            <ChevronDown 
              size={14} 
              style={{ 
                color: '#94A3B8', 
                transform: userMenuOpen ? 'rotate(180deg)' : 'none', 
                transition: 'transform 0.15s ease' 
              }} 
            />
          </div>

          {/* Upward Dropdown Menu */}
          {userMenuOpen && (
            <>
              <div 
                onClick={() => setUserMenuOpen(false)}
                style={{ position: 'fixed', inset: 0, zIndex: 50 }}
              />
              <div style={{
                position: 'absolute',
                bottom: 'calc(100% + 8px)',
                left: 0,
                right: 0,
                background: '#FFFFFF',
                border: '1px solid #E2E8F0',
                borderRadius: 10,
                boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.12), 0 8px 10px -6px rgba(0, 0, 0, 0.08)',
                padding: '8px 0',
                zIndex: 60,
                animation: 'fadeIn 0.15s ease'
              }}>
                {/* Profile Details */}
                <div style={{ padding: '8px 14px 10px', borderBottom: '1px solid #F1F5F9' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                      width: 32,
                      height: 32,
                      borderRadius: 8,
                      background: '#EF4444',
                      color: '#FFFFFF',
                      display: 'grid',
                      placeItems: 'center',
                      flexShrink: 0
                    }}>
                      <User size={16} strokeWidth={2.5} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <strong style={{ fontSize: 12.5, color: '#0F172A', display: 'block', lineHeight: 1.2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Nikhil Raikwar</strong>
                      <span style={{ fontSize: 11, color: '#64748B', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>nikhil@planproof.dev</span>
                    </div>
                  </div>
                  <div style={{ marginTop: 6, display: 'inline-flex', alignItems: 'center', gap: 4, background: '#FFF1EB', border: '1px solid #FFD9CA', color: '#EA580C', fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4 }}>
                    <span>Personal Workspace</span>
                  </div>
                </div>

                {/* Divider & Sign out */}
                <div style={{ padding: '6px' }}>
                  <Link
                    href="/"
                    onClick={() => setUserMenuOpen(false)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '8px 12px',
                      borderRadius: 6,
                      fontSize: 12.5,
                      fontWeight: 700,
                      color: '#DC2626',
                      textDecoration: 'none',
                      transition: 'all 0.15s ease'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = '#FEF2F2'
                      e.currentTarget.style.color = '#B91C1C'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent'
                      e.currentTarget.style.color = '#DC2626'
                    }}
                  >
                    <LogOut size={14} />
                    <span>Sign Out</span>
                  </Link>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </aside>
  )
}

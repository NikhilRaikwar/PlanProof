'use client'

import React, { useState } from 'react'
import { AppSidebar } from '@/components/app-sidebar'
import { AppTopbar } from '@/components/app-topbar'
import { WorkspaceProvider } from '@/components/workspace-context'

export function WorkspaceShell({
  children,
}: {
  children: React.ReactNode
}) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <WorkspaceProvider>
      <div className="app-shell">
        {/* Sidebar */}
        <AppSidebar
          mobileOpen={mobileMenuOpen}
          onCloseMobile={() => setMobileMenuOpen(false)}
        />

        {/* Main Content View with Topbar */}
        <div
          className="app-main-area"
          style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}
        >
          <AppTopbar onToggleMobile={() => setMobileMenuOpen(!mobileMenuOpen)} />
          <main className="app-content-wrap">{children}</main>
        </div>
      </div>
    </WorkspaceProvider>
  )
}

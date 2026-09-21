'use client'

import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppSidebar } from '@/components/app-sidebar'
import { AppTopbar } from '@/components/app-topbar'
import { api } from '@/lib/api'

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    void api.session()
      .catch(() => {
        router.push('/')
      })
  }, [router])

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <AppSidebar 
        mobileOpen={mobileMenuOpen} 
        onCloseMobile={() => setMobileMenuOpen(false)} 
      />

      {/* Main Content View with Topbar */}
      <div className="app-main-area" style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <AppTopbar onToggleMobile={() => setMobileMenuOpen(!mobileMenuOpen)} />
        <main className="app-content-wrap">
          {children}
        </main>
      </div>
    </div>
  )
}

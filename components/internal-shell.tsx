'use client'

import React from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { ArrowLeft } from 'lucide-react'

export function InternalShell({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#FBF9F5',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Internal Engineering Header Strip */}
      <header
        style={{
          background: '#FFFFFF',
          borderBottom: '1px solid #E2E8F0',
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <Link
            href="/workspace/new-verification"
            style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none' }}
          >
            <div className="nav-logo-box" style={{ width: 26, height: 26 }}>
              <Image src="/logo.png" alt="PlanProof" width={24} height={24} priority />
            </div>
            <strong style={{ fontSize: 14, fontWeight: 800, color: '#0F172A' }}>
              PlanProof
            </strong>
          </Link>
          <span style={{ color: '#CBD5E1' }}>/</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                fontSize: 10,
                fontWeight: 850,
                padding: '2px 8px',
                borderRadius: 4,
                background: '#FEF3C7',
                color: '#92400E',
                border: '1px solid #FDE68A',
                letterSpacing: '0.4px',
              }}
            >
              INTERNAL ENGINEERING
            </span>
            <span style={{ fontSize: 13, fontWeight: 700, color: '#475569' }}>
              Quality & Reliability Benchmarks
            </span>
          </div>
        </div>

        <Link
          href="/workspace/new-verification"
          className="btn-plan-action"
          style={{ textDecoration: 'none', padding: '6px 12px', fontSize: 12 }}
        >
          <ArrowLeft size={13} />
          <span>Back to User Workspace</span>
        </Link>
      </header>

      {/* Internal View Container */}
      <main
        style={{
          maxWidth: 1200,
          width: '100%',
          margin: '0 auto',
          padding: '24px 20px',
          flex: 1,
        }}
      >
        {children}
      </main>
    </div>
  )
}

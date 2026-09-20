'use client'

import React from 'react'
import { ShieldAlert, ShieldCheck } from 'lucide-react'

export interface RunSummaryBannerProps {
  status: 'BLOCKED' | 'VERIFIED'
  coverage: number
  disprovedCount: number
  verifiedCount?: number
  isHumanResolved?: boolean
}

export function RunSummaryBanner({
  status,
  coverage = 83,
  disprovedCount = 2,
  isHumanResolved = false
}: RunSummaryBannerProps) {
  const isBlocked = status === 'BLOCKED' && !isHumanResolved && disprovedCount > 0

  return (
    <div style={{
      padding: '18px 22px',
      borderRadius: 12,
      border: isBlocked ? '1px solid #FECACA' : '1px solid #A7F3D0',
      background: isBlocked ? '#FEF2F2' : '#ECFDF5',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      flexWrap: 'wrap',
      gap: 16
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{
          width: 40,
          height: 40,
          borderRadius: 10,
          display: 'grid',
          placeItems: 'center',
          flexShrink: 0,
          background: isBlocked ? '#FEE2E2' : '#D1FAE5',
          color: isBlocked ? '#DC2626' : '#059669'
        }}>
          {isBlocked ? <ShieldAlert size={22} /> : <ShieldCheck size={22} />}
        </div>
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 800, color: '#0F172A', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span>Plan Status:</span>
            <span style={{
              fontSize: 11,
              fontWeight: 850,
              padding: '2px 8px',
              borderRadius: 4,
              background: isBlocked ? '#FEE2E2' : '#D1FAE5',
              color: isBlocked ? '#991B1B' : '#065F46'
            }}>
              {isBlocked ? 'BLOCKED BEFORE EXECUTION' : 'VERIFIED / READY FOR AGENTS'}
            </span>
          </h2>
          <p style={{ fontSize: 12, color: '#475569', margin: '4px 0 0' }}>
            {isBlocked ? (
              '2 critical obligations contradict codebase evidence. Review counter-evidence and apply remediations before implementation.'
            ) : (
              'All critical obligations verified against codebase evidence. Safe for autonomous agent execution.'
            )}
          </p>
        </div>
      </div>

      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 24, fontWeight: 850, color: '#0F172A', fontFamily: 'var(--font-mono)' }}>{coverage}%</div>
        <div style={{ fontSize: 11, color: '#64748B', fontWeight: 650 }}>Verification Coverage</div>
      </div>
    </div>
  )
}

'use client'

import React from 'react'
import { ShieldAlert, ShieldCheck } from 'lucide-react'

export interface RunSummaryBannerProps {
  status: 'BLOCKED' | 'VERIFIED_FOR_EXECUTION' | 'HUMAN_DECISION_REQUIRED' | 'INCONCLUSIVE' | 'FAILED'
  disprovedCount: number
  verifiedCount: number
}

export function RunSummaryBanner({
  status,
  disprovedCount,
  verifiedCount,
}: RunSummaryBannerProps) {
  const isBlocked = status === 'BLOCKED'
  const label = status.replaceAll('_', ' ')

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
              {label}
            </span>
          </h2>
          <p style={{ fontSize: 12, color: '#475569', margin: '4px 0 0' }}>
            {isBlocked ? (
              `${disprovedCount} obligation${disprovedCount === 1 ? '' : 's'} contradict${disprovedCount === 1 ? 's' : ''} repository evidence. Review counter-evidence before implementation.`
            ) : (
              `${verifiedCount} obligation${verifiedCount === 1 ? '' : 's'} are verified by the persisted backend policy.`
            )}
          </p>
        </div>
      </div>

      <div style={{ textAlign: 'right', fontSize: 12, color: '#64748B' }}>Verified: {verifiedCount}</div>
    </div>
  )
}

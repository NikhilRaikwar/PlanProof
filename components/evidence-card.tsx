'use client'

import React from 'react'
import { StatusBadge } from './status-badge'
import { EvidenceItem } from '@/lib/data'

export interface EvidenceCardProps {
  item: EvidenceItem
  isSelected?: boolean
  onClick?: () => void
}

export function EvidenceCard({ item, isSelected = false, onClick }: EvidenceCardProps) {
  return (
    <button
      onClick={onClick}
      className={`evidence-item-btn ${isSelected ? 'selected' : ''}`}
      type="button"
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 800, color: '#94A3B8' }}>{item.indexStr}</span>
        <div>
          <strong style={{ fontSize: 12.5, fontWeight: 750, color: '#0F172A', display: 'block', lineHeight: 1.3 }}>{item.title}</strong>
          <span style={{ fontSize: 11, color: '#64748B', fontFamily: 'var(--font-mono)', display: 'block', margin: '2px 0 3px' }}>{item.sourcePath}</span>
          <p style={{ fontSize: 11.5, color: '#475569', margin: 0, lineHeight: 1.35 }}>{item.summaryFact}</p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6, flexShrink: 0 }}>
        <StatusBadge status={item.status} size="sm" />
        <span style={{ fontSize: 10.5, color: '#94A3B8', fontFamily: 'var(--font-mono)' }}>{item.sourceType} · Lines {item.lines}</span>
      </div>
    </button>
  )
}

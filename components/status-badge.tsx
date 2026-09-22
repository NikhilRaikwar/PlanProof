'use client'

import React from 'react'
import { CheckCircle2, XCircle, AlertTriangle, Clock3 } from 'lucide-react'

export interface StatusBadgeProps {
  status: 'verified' | 'disproved' | 'human' | 'inconclusive' | string
  size?: 'sm' | 'md'
  showIcon?: boolean
}

export function StatusBadge({ status, size = 'md', showIcon = true }: StatusBadgeProps) {
  const norm = status.toLowerCase()
  if (norm === 'verified' || norm === 'complete' || norm === 'ready') {
    return (
      <span className={`badge-pill-base badge-verified ${size === 'sm' ? 'text-[9.5px] px-1.5 py-0.5' : ''}`}>
        {showIcon && <CheckCircle2 size={12} />}
        <span>VERIFIED</span>
      </span>
    )
  }
  if (norm === 'disproved' || norm === 'blocked' || norm === 'failed') {
    return (
      <span className={`badge-pill-base badge-blocked ${size === 'sm' ? 'text-[9.5px] px-1.5 py-0.5' : ''}`}>
        {showIcon && <XCircle size={12} />}
        <span>{norm === 'disproved' ? 'DISPROVED' : norm.toUpperCase()}</span>
      </span>
    )
  }
  if (norm === 'human' || norm === 'human required' || norm === 'human_required' || norm === 'human_wait' || norm === 'human decision required') {
    return (
      <span className={`badge-pill-base badge-human ${size === 'sm' ? 'text-[9.5px] px-1.5 py-0.5' : ''}`}>
        {showIcon && <AlertTriangle size={12} />}
        <span>HUMAN DECISION REQUIRED</span>
      </span>
    )
  }
  return (
    <span className={`badge-pill-base badge-inconclusive ${size === 'sm' ? 'text-[9.5px] px-1.5 py-0.5' : ''}`}>
      {showIcon && <Clock3 size={12} />}
      <span>{status.toUpperCase().replaceAll('_', ' ')}</span>
    </span>
  )
}

'use client'

import React from 'react'
import { CheckCircle2, XCircle, AlertTriangle, Clock3 } from 'lucide-react'

export interface StatusBadgeProps {
  status: 'verified' | 'disproved' | 'human' | 'inconclusive' | string
  size?: 'sm' | 'md'
  showIcon?: boolean
}

export function StatusBadge({ status, size = 'md', showIcon = true }: StatusBadgeProps) {
  switch (status.toLowerCase()) {
    case 'verified':
      return (
        <span className={`status-badge status-verified ${size === 'sm' ? 'text-[9.5px] px-1.5 py-0.5' : ''}`}>
          {showIcon && <CheckCircle2 size={size === 'sm' ? 10 : 12} />}
          <span>VERIFIED</span>
        </span>
      )
    case 'disproved':
      return (
        <span className={`status-badge status-disproved ${size === 'sm' ? 'text-[9.5px] px-1.5 py-0.5' : ''}`}>
          {showIcon && <XCircle size={size === 'sm' ? 10 : 12} />}
          <span>DISPROVED</span>
        </span>
      )
    case 'human':
    case 'human required':
      return (
        <span className={`status-badge status-human ${size === 'sm' ? 'text-[9.5px] px-1.5 py-0.5' : ''}`}>
          {showIcon && <AlertTriangle size={size === 'sm' ? 10 : 12} />}
          <span>HUMAN REQUIRED</span>
        </span>
      )
    default:
      return (
        <span className={`status-badge status-inconclusive ${size === 'sm' ? 'text-[9.5px] px-1.5 py-0.5' : ''}`}>
          {showIcon && <Clock3 size={size === 'sm' ? 10 : 12} />}
          <span>INCONCLUSIVE</span>
        </span>
      )
  }
}

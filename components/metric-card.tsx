'use client'

import React from 'react'
import { Info } from 'lucide-react'

export interface MetricCardProps {
  label: string
  value: string | number
  subtext?: string
  trend?: string
  trendType?: 'positive' | 'negative' | 'neutral'
  hasInfo?: boolean
}

export function MetricCard({
  label,
  value,
  subtext,
  trend,
  trendType = 'positive',
  hasInfo = false
}: MetricCardProps) {
  const trendColor = trendType === 'positive' ? '#059669' : trendType === 'negative' ? '#DC2626' : '#64748B'

  return (
    <div className="evals-kpi-card">
      <span style={{ fontSize: 10.5, fontWeight: 750, color: '#64748B', display: 'flex', alignItems: 'center', gap: 4 }}>
        {label} {hasInfo && <Info size={11} style={{ color: '#94A3B8' }} />}
      </span>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, margin: '4px 0 2px' }}>
        <strong style={{ fontSize: 22, color: '#0F172A', fontFamily: 'var(--font-mono)' }}>{value}</strong>
        {trend && (
          <span style={{ fontSize: 11, fontWeight: 700, color: trendColor }}>
            {trend}
          </span>
        )}
      </div>
      {subtext && <span style={{ fontSize: 10.5, color: '#64748B' }}>{subtext}</span>}
    </div>
  )
}

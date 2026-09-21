"use client"

import { ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'

import { api, ApiError, EvaluationRun } from '@/lib/api'

export default function InternalQualityPage() {
  const [run, setRun] = useState<EvaluationRun | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { api.latestEvaluation().then(setRun).catch(e => setError(e instanceof ApiError && e.status === 404 ? '' : 'Evaluation results are unavailable.')) }, [])
  return <div className="card-panel-white" style={{ textAlign: 'center', padding: 64 }}>
    <ShieldCheck size={28} style={{ color: '#EA580C' }} />
    <h1 className="page-main-title">Internal quality</h1>
    {error ? <p className="page-main-desc">{error}</p> : !run ? <p className="page-main-desc">No evaluation runs recorded yet.</p> : <>
      <p className="page-main-desc">Latest recorded evaluation: {run.sample_count} cases at {new Date(run.timestamp).toLocaleString()}.</p>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 16, flexWrap: 'wrap' }}>{Object.entries(run.metrics).map(([name, value]) => <span key={name} className="mono-label">{name}: {typeof value === 'number' ? value.toFixed(3) : value}</span>)}</div>
      {run.limitations.map(item => <p key={item} className="page-main-desc">{item}</p>)}
    </>}
  </div>
}

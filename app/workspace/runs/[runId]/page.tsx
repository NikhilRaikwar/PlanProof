'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import {
  AlertOctagon,
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  Plus,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
} from 'lucide-react'
import { defaultObligations, Obligation } from '@/lib/data'
import { StatusBadge } from '@/components/status-badge'
import { RunSummaryBanner } from '@/components/run-summary'
import { CodeBlock } from '@/components/code-block'

export default function RunReportPage() {
  const [obligationsList, setObligationsList] = useState<Obligation[]>(defaultObligations)
  const [selectedObligationId, setSelectedObligationId] = useState<string>('ob-1')
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'disproved' | 'verified' | 'human' | 'inconclusive'>('ALL')
  const [humanDecisionSelected, setHumanDecisionSelected] = useState<string>('')
  const [humanDecisionSubmitted, setHumanDecisionSubmitted] = useState(false)
  const [copiedPrompt, setCopiedPrompt] = useState(false)

  const selectedObligation = obligationsList.find(o => o.id === selectedObligationId) || obligationsList[0]

  const disprovedCount = obligationsList.filter(o => o.status === 'disproved').length
  const verifiedCount = obligationsList.filter(o => o.status === 'verified').length
  const humanCount = obligationsList.filter(o => o.status === 'human').length
  const inconclusiveCount = obligationsList.filter(o => o.status === 'inconclusive').length
  const totalCount = obligationsList.length

  const filteredObligations = obligationsList.filter(o => {
    if (statusFilter === 'ALL') return true
    return o.status === statusFilter
  })

  const handleResolveHumanDecision = () => {
    if (!humanDecisionSelected) return
    setHumanDecisionSubmitted(true)
    setObligationsList(prev => prev.map(o => {
      if (o.id === 'ob-3') {
        return {
          ...o,
          status: 'verified',
          rationale: `Resolved by Tech Lead: "${humanDecisionSelected}". Policy verified against authentication gate.`
        }
      }
      return o
    }))
  }

  const handleCopyAgentPrompt = () => {
    const promptPayload = `[PLANPROOF VERIFICATION GATE REPORT - Commit: 8f3c1a2]
Repository: nikhilraikwar / planproof
Plan Status: ${disprovedCount > 0 && !humanDecisionSubmitted ? 'BLOCKED' : 'VERIFIED'}
Verification Coverage: 83%

CRITICAL DISPROVED ASSUMPTIONS:
${obligationsList.filter(o => o.status === 'disproved').map((o, idx) => `
${idx + 1}. [${o.category}] ${o.title}
   Location: ${o.file} (${o.lineRange})
   Evidence: ${o.counterEvidence}
   Fix: ${o.remediation}
`).join('')}

INSTRUCTION FOR CODING AGENT:
Apply the remediations specified above before executing code changes.`

    navigator.clipboard.writeText(promptPayload)
    setCopiedPrompt(true)
    setTimeout(() => setCopiedPrompt(false), 2500)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div className="preflight-eyebrow">
            <ShieldCheck size={13} />
            <span>PRE-FLIGHT GATE REPORT • COMMIT 8F3C1A2</span>
          </div>
          <h1 className="page-main-title" style={{ fontSize: 24, margin: '2px 0 4px' }}>
            Partial Refunds <span style={{ color: '#CBD5E1', fontWeight: 300 }}>/</span> Plan Gate
          </h1>
          <p className="page-main-desc" style={{ margin: 0, fontSize: 12.5 }}>
            nikhilraikwar / planproof • branch: main • Plan v1.0 • Completed just now
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button 
            onClick={handleCopyAgentPrompt}
            className="btn-plan-action"
            style={{ padding: '7px 12px', fontSize: 12 }}
          >
            {copiedPrompt ? <Check size={13} style={{ color: '#059669' }} /> : <Copy size={13} />}
            <span>{copiedPrompt ? 'Copied!' : 'Copy Agent Prompt'}</span>
          </button>

          <Link 
            href="/workspace/new-verification"
            className="btn-verify-plan-cta"
            style={{ textDecoration: 'none', padding: '7px 14px', fontSize: 12 }}
          >
            <Plus size={14} />
            <span>New Verification</span>
          </Link>
        </div>
      </div>

      {/* Plan Gate Banner */}
      <RunSummaryBanner 
        status="BLOCKED"
        coverage={83}
        disprovedCount={disprovedCount}
        isHumanResolved={humanDecisionSubmitted}
      />

      {/* KPI Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 12 }}>
        <div className="card-panel-white" style={{ padding: '12px 16px' }}>
          <span style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block' }}>Claims Extracted</span>
          <strong style={{ fontSize: 20, fontWeight: 850, color: '#0F172A', fontFamily: 'var(--font-mono)', display: 'block', marginTop: 2 }}>{totalCount}</strong>
        </div>

        <div className="card-panel-white" style={{ padding: '12px 16px' }}>
          <span style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block' }}>Verified</span>
          <strong style={{ fontSize: 20, fontWeight: 850, color: '#059669', fontFamily: 'var(--font-mono)', display: 'block', marginTop: 2 }}>{verifiedCount}</strong>
        </div>

        <div className="card-panel-white" style={{ padding: '12px 16px' }}>
          <span style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block' }}>Disproved</span>
          <strong style={{ fontSize: 20, fontWeight: 850, color: '#DC2626', fontFamily: 'var(--font-mono)', display: 'block', marginTop: 2 }}>{disprovedCount}</strong>
        </div>

        <div className="card-panel-white" style={{ padding: '12px 16px' }}>
          <span style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block' }}>Human Required</span>
          <strong style={{ fontSize: 20, fontWeight: 850, color: '#D97706', fontFamily: 'var(--font-mono)', display: 'block', marginTop: 2 }}>{humanCount}</strong>
        </div>

        <div className="card-panel-white" style={{ padding: '12px 16px' }}>
          <span style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block' }}>Inconclusive</span>
          <strong style={{ fontSize: 20, fontWeight: 850, color: '#64748B', fontFamily: 'var(--font-mono)', display: 'block', marginTop: 2 }}>{inconclusiveCount}</strong>
        </div>
      </div>

      {/* Master Detail Inspector */}
      <div className="dashboard-two-col-grid" style={{ gridTemplateColumns: '1.2fr 1.8fr', gap: 20 }}>
        {/* Obligations List */}
        <div className="card-panel-white" style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <h3 style={{ fontSize: 12.5, fontWeight: 800, color: '#0F172A', margin: 0 }}>Proof Obligations ({filteredObligations.length})</h3>
            <div style={{ display: 'flex', gap: 4 }}>
              <button 
                onClick={() => setStatusFilter('ALL')}
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: 4,
                  border: 'none',
                  cursor: 'pointer',
                  background: statusFilter === 'ALL' ? '#0F172A' : 'transparent',
                  color: statusFilter === 'ALL' ? '#FFFFFF' : '#64748B'
                }}
              >
                All
              </button>
              <button 
                onClick={() => setStatusFilter('disproved')}
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: 4,
                  border: 'none',
                  cursor: 'pointer',
                  background: statusFilter === 'disproved' ? '#DC2626' : 'transparent',
                  color: statusFilter === 'disproved' ? '#FFFFFF' : '#64748B'
                }}
              >
                Disproved
              </button>
              <button 
                onClick={() => setStatusFilter('human')}
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: 4,
                  border: 'none',
                  cursor: 'pointer',
                  background: statusFilter === 'human' ? '#D97706' : 'transparent',
                  color: statusFilter === 'human' ? '#FFFFFF' : '#64748B'
                }}
              >
                Human
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {filteredObligations.map((item, idx) => {
              const isSelected = item.id === selectedObligation.id
              return (
                <button 
                  key={item.id}
                  onClick={() => setSelectedObligationId(item.id)}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    padding: 12,
                    borderRadius: 8,
                    border: isSelected ? '1.5px solid #EA580C' : '1px solid #E2E8F0',
                    background: isSelected ? '#FFF7ED' : '#FFFFFF',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: 10
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 800, color: '#94A3B8' }}>0{idx + 1}</span>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <span style={{ fontSize: 9.5, fontWeight: 800, color: '#64748B', background: '#F1F5F9', padding: '1px 5px', borderRadius: 3, textTransform: 'uppercase' }}>
                          {item.category}
                        </span>
                      </div>
                      <strong style={{ fontSize: 12, fontWeight: 750, color: '#0F172A', display: 'block', lineHeight: 1.3 }}>{item.title}</strong>
                      <span style={{ fontSize: 11, color: '#64748B', display: 'block', marginTop: 2, fontFamily: 'var(--font-mono)' }}>{item.file}</span>
                    </div>
                  </div>
                  <div><StatusBadge status={item.status} size="sm" /></div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Obligation Detail Panel */}
        <div className="card-panel-white" style={{ padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', borderBottom: '1px solid #F1F5F9', paddingBottom: 14, marginBottom: 16 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 10, fontWeight: 800, background: '#F1F5F9', color: '#475569', padding: '2px 6px', borderRadius: 4, textTransform: 'uppercase' }}>
                  {selectedObligation.category}
                </span>
                <span style={{ fontSize: 10, fontWeight: 800, background: '#FEE2E2', color: '#991B1B', padding: '2px 6px', borderRadius: 4 }}>
                  {selectedObligation.criticality}
                </span>
              </div>
              <h2 style={{ fontSize: 16, fontWeight: 850, color: '#0F172A', margin: 0 }}>{selectedObligation.title}</h2>
              <div style={{ fontSize: 11, color: '#64748B', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                Target: <strong>{selectedObligation.file}</strong> ({selectedObligation.lineRange})
              </div>
            </div>
            <div><StatusBadge status={selectedObligation.status} /></div>
          </div>

          {/* Rationale */}
          <div style={{ marginBottom: 16 }}>
            <span style={{ fontSize: 11, fontWeight: 800, color: '#475569', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>Assumption vs Codebase Reality</span>
            <p style={{ fontSize: 12.5, color: '#1E293B', lineHeight: 1.5, margin: 0 }}>{selectedObligation.rationale}</p>
          </div>

          {/* Counter Evidence Callout if Disproved */}
          {selectedObligation.counterEvidence && (
            <div style={{ background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 8, padding: 12, marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 800, color: '#B91C1C', textTransform: 'uppercase', marginBottom: 4 }}>
                <AlertOctagon size={13} />
                <span>Counter Evidence Found</span>
              </div>
              <p style={{ fontSize: 12, color: '#991B1B', lineHeight: 1.4, margin: 0 }}>{selectedObligation.counterEvidence}</p>
            </div>
          )}

          {/* Code Snippet */}
          {selectedObligation.codeSnippet && (
            <div style={{ marginBottom: 16 }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: '#475569', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>Codebase Evidence</span>
              <CodeBlock 
                code={selectedObligation.codeSnippet}
                filePath={selectedObligation.file}
                lines={selectedObligation.lineRange}
              />
            </div>
          )}

          {/* Human Decision Resolver */}
          {selectedObligation.humanDecisionPrompt && !humanDecisionSubmitted && (
            <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 8, padding: 14, marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 800, color: '#B45309', textTransform: 'uppercase', marginBottom: 6 }}>
                <UserCheck size={14} />
                <span>Human-In-The-Loop Decision Required</span>
              </div>
              <p style={{ fontSize: 12.5, fontWeight: 700, color: '#92400E', margin: '0 0 10px' }}>{selectedObligation.humanDecisionPrompt.question}</p>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {selectedObligation.humanDecisionPrompt.options.map((option, idx) => (
                  <label key={idx} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#78350F', cursor: 'pointer', background: '#FEF3C7', padding: '6px 10px', borderRadius: 6 }}>
                    <input 
                      type="radio" 
                      name="human-decision"
                      checked={humanDecisionSelected === option}
                      onChange={() => setHumanDecisionSelected(option)}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>

              <button 
                onClick={handleResolveHumanDecision}
                disabled={!humanDecisionSelected}
                style={{
                  marginTop: 10,
                  background: humanDecisionSelected ? '#D97706' : '#FDE68A',
                  color: '#FFFFFF',
                  fontSize: 11.5,
                  fontWeight: 750,
                  padding: '6px 14px',
                  borderRadius: 6,
                  border: 'none',
                  cursor: humanDecisionSelected ? 'pointer' : 'not-allowed'
                }}
              >
                Apply Decision & Re-verify Gate
              </button>
            </div>
          )}

          {/* Remediation Plan */}
          {selectedObligation.remediation && (
            <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 8, padding: 12 }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: '#475569', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>Proposed Plan Amendment</span>
              <p style={{ fontSize: 12, color: '#334155', lineHeight: 1.4, margin: 0 }}>{selectedObligation.remediation}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

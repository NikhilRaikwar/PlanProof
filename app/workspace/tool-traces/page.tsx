'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock,
  Code2,
  Database,
  FileCode2,
  FileText,
  Network,
  Scale,
  Search,
  Terminal,
  Zap,
} from 'lucide-react'
import { defaultToolTraces, ToolTraceItem } from '@/lib/data'
import { CodeBlock } from '@/components/code-block'

export default function ToolTracesPage() {
  const [selectedToolIndex, setSelectedToolIndex] = useState(0)
  const [activeTab, setActiveTab] = useState<'Overview' | 'Inputs' | 'Outputs' | 'Evidence (6)' | 'Trace log'>('Overview')

  const toolIcons: Record<string, any> = {
    'claim_extraction': FileText,
    'symbol_search': Search,
    'schema_probe': Database,
    'dependency_graph': Network,
    'openapi_scan': Code2,
    'contradiction_check': Scale
  }

  const selectedTool = defaultToolTraces[selectedToolIndex] || defaultToolTraces[0]
  const IconComponent = toolIcons[selectedTool.name] || Terminal

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
        <div>
          <div className="preflight-eyebrow">
            <Terminal size={13} />
            <span>EXECUTION TELEMETRY</span>
          </div>
          <h1 className="page-main-title">Tool traces</h1>
          <p className="page-main-desc" style={{ margin: 0 }}>
            Deterministic AST probes, semantic search, and schema analyzers executed in order during verification run #101.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Link
            href="/workspace/runs/run-101"
            className="btn-plan-action"
            style={{ padding: '7px 12px', fontSize: 12, textDecoration: 'none' }}
          >
            <ArrowLeft size={13} />
            <span>Back to Run #101</span>
          </Link>
          <Link
            href="/workspace/new-verification"
            className="btn-verify-plan-cta"
            style={{ padding: '7px 14px', fontSize: 12, textDecoration: 'none' }}
          >
            <span>New Verification</span>
            <ArrowRight size={13} />
          </Link>
        </div>
      </div>

      {/* Summary Strip (Stat Pills) */}
      <div className="card-panel-white" style={{ padding: '12px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 800, color: '#0F172A' }}>Pipeline Summary:</span>
            <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4, background: '#F1F5F9', color: '#475569' }}>
              6 Tools Executed
            </span>
            <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4, background: '#F1F5F9', color: '#475569', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Clock size={11} /> 1m 24s total
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 800, padding: '2px 8px', borderRadius: 4, background: '#FEE2E2', color: '#991B1B' }}>
              2 Disproved
            </span>
            <span style={{ fontSize: 11, fontWeight: 800, padding: '2px 8px', borderRadius: 4, background: '#FEF3C7', color: '#92400E' }}>
              1 Human Required
            </span>
            <span style={{ fontSize: 11, fontWeight: 800, padding: '2px 8px', borderRadius: 4, background: '#F1F5F9', color: '#475569' }}>
              1 Inconclusive
            </span>
          </div>
        </div>
      </div>

      {/* Two Column Trace Inspector */}
      <div className="dashboard-two-col-grid" style={{ gridTemplateColumns: '1.2fr 1.8fr', gap: 20 }}>
        {/* Left Column: Ordered Tool Execution List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 750, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 2 }}>
            Execution Sequence (6 Steps)
          </div>

          {defaultToolTraces.map((tool, idx) => {
            const isSelected = idx === selectedToolIndex
            const ToolIcon = toolIcons[tool.name] || Terminal

            return (
              <button
                key={tool.id}
                onClick={() => setSelectedToolIndex(idx)}
                style={{
                  width: '100%',
                  textAlign: 'left',
                  padding: '12px 14px',
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
                  <div style={{
                    width: 28,
                    height: 28,
                    borderRadius: 6,
                    background: isSelected ? '#FFEDD5' : '#F1F5F9',
                    color: isSelected ? '#EA580C' : '#475569',
                    display: 'grid',
                    placeItems: 'center',
                    flexShrink: 0
                  }}>
                    <ToolIcon size={14} />
                  </div>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 800, color: '#94A3B8' }}>0{idx + 1}</span>
                      <strong style={{ fontSize: 12.5, fontWeight: 750, color: '#0F172A', fontFamily: 'var(--font-mono)' }}>{tool.name}</strong>
                    </div>
                    <p style={{ fontSize: 11.5, color: '#64748B', margin: '3px 0 0', lineHeight: 1.35 }}>{tool.desc}</p>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, fontWeight: 800, color: '#059669', background: '#ECFDF5', padding: '1px 6px', borderRadius: 4 }}>
                    <CheckCircle2 size={10} /> DONE
                  </span>
                  <span style={{ fontSize: 10.5, color: '#94A3B8', fontFamily: 'var(--font-mono)' }}>{tool.duration}</span>
                </div>
              </button>
            )
          })}

          {defaultToolTraces.length === 0 && (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: '40px 20px', color: '#64748B' }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: '#FFF1EB', color: '#EA580C', display: 'grid', placeItems: 'center', margin: '0 auto 10px' }}>
                <Terminal size={20} />
              </div>
              <h3 style={{ fontSize: 15, fontWeight: 800, color: '#0F172A', margin: '0 0 4px' }}>No tool trace selected</h3>
              <p style={{ fontSize: 12, color: '#64748B', maxWidth: 300, margin: '0 auto 12px' }}>
                Select a verification run to inspect its execution trace and AST telemetry.
              </p>
              <Link
                href="/workspace/runs"
                className="btn-plan-action"
                style={{ textDecoration: 'none', display: 'inline-flex', padding: '6px 14px', fontSize: 11.5 }}
              >
                <span>View runs</span>
              </Link>
            </div>
          )}
        </div>

        {/* Right Column: Tabbed Trace Inspector */}
        <div className="card-panel-white" style={{ padding: 22 }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', borderBottom: '1px solid #F1F5F9', paddingBottom: 14, marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 34, height: 34, borderRadius: 8, background: '#FFF1EB', color: '#EA580C', display: 'grid', placeItems: 'center', flexShrink: 0 }}>
                <IconComponent size={18} />
              </div>
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 850, color: '#0F172A', margin: 0, fontFamily: 'var(--font-mono)' }}>
                  {selectedTool.name}
                </h2>
                <span style={{ fontSize: 11, color: '#64748B' }}>
                  Step {selectedToolIndex + 1} of 6 • Duration: {selectedTool.duration}
                </span>
              </div>
            </div>

            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 800, color: '#059669', background: '#D1FAE5', padding: '2px 8px', borderRadius: 4 }}>
              <CheckCircle2 size={12} /> COMPLETED
            </span>
          </div>

          {/* Tab Navigation */}
          <div style={{ display: 'flex', gap: 6, borderBottom: '1px solid #E2E8F0', paddingBottom: 8, marginBottom: 16 }}>
            {(['Overview', 'Inputs', 'Outputs', 'Evidence (6)', 'Trace log'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: '5px 12px',
                  borderRadius: 6,
                  fontSize: 11.5,
                  fontWeight: 700,
                  border: 'none',
                  cursor: 'pointer',
                  background: activeTab === tab ? '#0F172A' : '#F1F5F9',
                  color: activeTab === tab ? '#FFFFFF' : '#64748B',
                  transition: 'all 0.15s ease'
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          {activeTab === 'Overview' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <span style={{ fontSize: 10.5, fontWeight: 800, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block', marginBottom: 4 }}>
                  Tool Purpose & Description
                </span>
                <p style={{ fontSize: 12.5, color: '#1E293B', lineHeight: 1.5, margin: 0 }}>
                  {selectedTool.desc}
                </p>
              </div>

              {/* 3 KPI Boxes */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                <div style={{ padding: '10px 12px', background: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: 10, color: '#94A3B8', fontWeight: 750, textTransform: 'uppercase', display: 'block' }}>AST Nodes</span>
                  <strong style={{ fontSize: 16, color: '#0F172A', fontFamily: 'var(--font-mono)' }}>142</strong>
                </div>
                <div style={{ padding: '10px 12px', background: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: 10, color: '#94A3B8', fontWeight: 750, textTransform: 'uppercase', display: 'block' }}>Claims Bound</span>
                  <strong style={{ fontSize: 16, color: '#0F172A', fontFamily: 'var(--font-mono)' }}>6</strong>
                </div>
                <div style={{ padding: '10px 12px', background: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: 10, color: '#94A3B8', fontWeight: 750, textTransform: 'uppercase', display: 'block' }}>Errors / Warns</span>
                  <strong style={{ fontSize: 16, color: '#059669', fontFamily: 'var(--font-mono)' }}>0 / 0</strong>
                </div>
              </div>

              {/* Outcome Summary */}
              <div style={{ background: '#ECFDF5', border: '1px solid #A7F3D0', borderRadius: 8, padding: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 800, color: '#065F46', textTransform: 'uppercase', marginBottom: 4 }}>
                  <CheckCircle2 size={13} />
                  <span>Execution Outcome</span>
                </div>
                <p style={{ fontSize: 12, color: '#047857', lineHeight: 1.45, margin: 0 }}>
                  Successfully evaluated all symbol references against <code>nikhilraikwar / planproof@8f3c1a2</code>. Output claims mapped to testable obligations.
                </p>
              </div>

              {/* Normalization Note */}
              <div style={{ padding: 12, background: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0', fontSize: 11.5, color: '#475569', lineHeight: 1.4 }}>
                <strong>Deterministic AST Grounding:</strong> PlanProof executes AST parses with strict syntax tree resolution. No external network requests were made during this step.
              </div>
            </div>
          )}

          {activeTab === 'Inputs' && (
            <div>
              <span style={{ fontSize: 10.5, fontWeight: 800, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block', marginBottom: 6 }}>
                Tool Input Payload (JSON)
              </span>
              <CodeBlock
                code={`{
  "tool": "${selectedTool.name}",
  "repo": "nikhilraikwar/planproof",
  "commit": "8f3c1a2",
  "plan_length_chars": 342,
  "parse_depth": "standard",
  "extract_symbols": true
}`}
                language="json"
              />
            </div>
          )}

          {activeTab === 'Outputs' && (
            <div>
              <span style={{ fontSize: 10.5, fontWeight: 800, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block', marginBottom: 6 }}>
                Tool Output Result (JSON)
              </span>
              <CodeBlock
                code={`{
  "status": "success",
  "symbols_matched": 142,
  "claims_generated": 6,
  "ast_call_depth": 4,
  "execution_duration_sec": 12.3,
  "findings": [
    { "claim": "PaymentService.refund", "line": 84, "conflict": true },
    { "claim": "RefundEntity.payment_id", "unique_constraint": true }
  ]
}`}
                language="json"
              />
            </div>
          )}

          {activeTab === 'Evidence (6)' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ fontSize: 10.5, fontWeight: 800, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block', marginBottom: 4 }}>
                Evidence Extracted By This Tool
              </span>
              <div style={{ padding: '8px 12px', background: '#F8FAFC', borderRadius: 6, border: '1px solid #E2E8F0', fontSize: 12 }}>
                <strong>services/payment.py:84-108</strong> — PaymentService hardcodes full captured_amount.
              </div>
              <div style={{ padding: '8px 12px', background: '#F8FAFC', borderRadius: 6, border: '1px solid #E2E8F0', fontSize: 12 }}>
                <strong>db/models/refund.ts:12-28</strong> — UNIQUE constraint on payment_id.
              </div>
            </div>
          )}

          {activeTab === 'Trace log' && (
            <div>
              <span style={{ fontSize: 10.5, fontWeight: 800, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block', marginBottom: 6 }}>
                Stdout & Execution Logs
              </span>
              <CodeBlock
                code={`[00:00:00.102] INIT tool=${selectedTool.name} PID=4892
[00:00:00.320] AST parser loading TypeScript and Python grammar trees...
[00:00:01.400] Parsing syntax graph from workspace cache (8f3c1a2)
[00:00:04.120] Walking AST: resolved 142 function signatures
[00:00:08.940] Evaluating claims against AST bindings...
[00:00:11.800] SUCCESS: Generated 6 proof obligations in ${selectedTool.duration}`}
                language="bash"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

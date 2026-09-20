'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileCode2,
  FileText,
  Filter,
  Info,
  Search,
} from 'lucide-react'
import { defaultEvidenceList, EvidenceItem } from '@/lib/data'
import { StatusBadge } from '@/components/status-badge'
import { EvidenceCard } from '@/components/evidence-card'
import { CodeBlock } from '@/components/code-block'

export default function EvidencePage() {
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>(defaultEvidenceList)
  const [selectedId, setSelectedId] = useState<string>(defaultEvidenceList[0].id)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [sourceTypeFilter, setSourceTypeFilter] = useState('ALL')

  const filteredList = evidenceList.filter(item => {
    const matchesSearch = item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          item.sourcePath.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          item.summaryFact.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesStatus = statusFilter === 'ALL' || item.status === statusFilter
    const matchesSource = sourceTypeFilter === 'ALL' || item.sourceType === sourceTypeFilter
    return matchesSearch && matchesStatus && matchesSource
  })

  const selectedIndex = filteredList.findIndex(e => e.id === selectedId)
  const safeIndex = selectedIndex >= 0 ? selectedIndex : 0
  const selectedItem = filteredList[safeIndex] || evidenceList[0]

  const handlePrev = () => {
    if (safeIndex > 0) {
      setSelectedId(filteredList[safeIndex - 1].id)
    }
  }

  const handleNext = () => {
    if (safeIndex < filteredList.length - 1) {
      setSelectedId(filteredList[safeIndex + 1].id)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Header */}
      <div>
        <div className="preflight-eyebrow">
          <FileText size={13} />
          <span>EVIDENCE EXPLORER</span>
        </div>
        <h1 className="page-main-title">Evidence explorer</h1>
        <p className="page-main-desc" style={{ margin: 0 }}>
          Repository facts, AST extractions, and schemas gathered during verification runs.
        </p>
      </div>

      {/* Filter Toolbar */}
      <div className="card-panel-white" style={{ padding: '12px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {/* Search Box */}
          <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#94A3B8' }} />
            <input 
              type="text"
              placeholder="Search evidence by symbol, file, or claim..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="custom-text-input"
              style={{ paddingLeft: 32, height: 34, fontSize: 12 }}
            />
          </div>

          {/* Status Filter */}
          <select 
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="custom-select-box"
            style={{ height: 34, padding: '0 10px', fontSize: 12, width: 'auto', minWidth: 130 }}
          >
            <option value="ALL">All Statuses</option>
            <option value="disproved">Disproved</option>
            <option value="verified">Verified</option>
            <option value="human">Human Required</option>
            <option value="inconclusive">Inconclusive</option>
          </select>

          {/* Source Type Filter */}
          <select 
            value={sourceTypeFilter}
            onChange={(e) => setSourceTypeFilter(e.target.value)}
            className="custom-select-box"
            style={{ height: 34, padding: '0 10px', fontSize: 12, width: 'auto', minWidth: 130 }}
          >
            <option value="ALL">All Sources</option>
            <option value="Code">Code</option>
            <option value="API Contract">API Contract</option>
            <option value="Business Rule">Business Rule</option>
          </select>

          {/* Target Run Preset */}
          <div style={{ fontSize: 11, color: '#64748B', display: 'flex', alignItems: 'center', gap: 6, background: '#F8FAFC', padding: '6px 10px', borderRadius: 6, border: '1px solid #E2E8F0' }}>
            <span>Run:</span>
            <strong style={{ color: '#0F172A', fontFamily: 'var(--font-mono)' }}>PlanGate #101</strong>
          </div>
        </div>
      </div>

      {/* Two Column Master Detail Grid */}
      <div className="dashboard-two-col-grid" style={{ gridTemplateColumns: '1.2fr 1.8fr', gap: 20 }}>
        {/* Left Column: Evidence List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 750, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 2 }}>
            Showing {filteredList.length} evidence items
          </div>

          {filteredList.map((item) => (
            <EvidenceCard
              key={item.id}
              item={item}
              isSelected={item.id === selectedItem?.id}
              onClick={() => setSelectedId(item.id)}
            />
          ))}

          {filteredList.length === 0 && (
            <div className="card-panel-white" style={{ textAlign: 'center', padding: '40px 20px', color: '#64748B' }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: '#FFF1EB', color: '#EA580C', display: 'grid', placeItems: 'center', margin: '0 auto 10px' }}>
                <FileText size={20} />
              </div>
              <h3 style={{ fontSize: 15, fontWeight: 800, color: '#0F172A', margin: '0 0 4px' }}>No evidence yet</h3>
              <p style={{ fontSize: 12, color: '#64748B', maxWidth: 300, margin: '0 auto 12px' }}>
                Run a verification to collect code-backed evidence and AST facts.
              </p>
              <Link
                href="/workspace/new-verification"
                className="btn-verify-plan-cta"
                style={{ textDecoration: 'none', display: 'inline-flex', padding: '6px 14px', fontSize: 11.5 }}
              >
                <span>New verification</span>
              </Link>
            </div>
          )}
        </div>

        {/* Right Column: Evidence Detail Panel */}
        {selectedItem && (
          <div className="card-panel-white" style={{ padding: 22 }}>
            {/* Header & Pagination */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', borderBottom: '1px solid #F1F5F9', paddingBottom: 14, marginBottom: 16 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 800, color: '#EA580C' }}>
                    EVIDENCE #{selectedItem.indexStr}
                  </span>
                  <StatusBadge status={selectedItem.status} size="sm" />
                </div>
                <h2 style={{ fontSize: 17, fontWeight: 850, color: '#0F172A', margin: 0 }}>
                  {selectedItem.title}
                </h2>
                <div style={{ fontSize: 11.5, color: '#64748B', fontFamily: 'var(--font-mono)', marginTop: 4 }}>
                  {selectedItem.sourcePath}
                </div>
              </div>

              {/* Pagination Controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <button
                  onClick={handlePrev}
                  disabled={safeIndex <= 0}
                  className="btn-plan-action"
                  style={{ padding: 6 }}
                  title="Previous evidence"
                >
                  <ChevronLeft size={14} />
                </button>
                <span style={{ fontSize: 11, color: '#64748B', fontFamily: 'var(--font-mono)' }}>
                  {safeIndex + 1} of {filteredList.length}
                </span>
                <button
                  onClick={handleNext}
                  disabled={safeIndex >= filteredList.length - 1}
                  className="btn-plan-action"
                  style={{ padding: 6 }}
                  title="Next evidence"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>

            {/* 4 Metadata Blocks Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, padding: '10px 12px', background: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0', marginBottom: 16 }}>
              <div>
                <span style={{ fontSize: 10, color: '#94A3B8', fontWeight: 750, textTransform: 'uppercase', display: 'block' }}>Source Type</span>
                <strong style={{ fontSize: 12, color: '#0F172A' }}>{selectedItem.sourceType}</strong>
              </div>
              <div>
                <span style={{ fontSize: 10, color: '#94A3B8', fontWeight: 750, textTransform: 'uppercase', display: 'block' }}>Language</span>
                <strong style={{ fontSize: 12, color: '#0F172A' }}>{selectedItem.language}</strong>
              </div>
              <div>
                <span style={{ fontSize: 10, color: '#94A3B8', fontWeight: 750, textTransform: 'uppercase', display: 'block' }}>Lines</span>
                <strong style={{ fontSize: 12, color: '#0F172A', fontFamily: 'var(--font-mono)' }}>{selectedItem.lines}</strong>
              </div>
              <div>
                <span style={{ fontSize: 10, color: '#94A3B8', fontWeight: 750, textTransform: 'uppercase', display: 'block' }}>Last Modified</span>
                <strong style={{ fontSize: 12, color: '#0F172A' }}>{selectedItem.lastModified}</strong>
              </div>
            </div>

            {/* Extracted Fact */}
            <div style={{ marginBottom: 16 }}>
              <span style={{ fontSize: 10.5, fontWeight: 800, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block', marginBottom: 4 }}>
                Extracted Fact
              </span>
              <p style={{ fontSize: 13, color: '#0F172A', lineHeight: 1.5, margin: 0, fontWeight: 550 }}>
                {selectedItem.summaryFact}
              </p>
            </div>

            {/* Why it Matters Callout */}
            <div style={{ background: '#FFF7ED', border: '1px solid #FFD9CA', borderRadius: 8, padding: 12, marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 800, color: '#EA580C', textTransform: 'uppercase', marginBottom: 4 }}>
                <Info size={13} />
                <span>Why it matters for plan execution</span>
              </div>
              <p style={{ fontSize: 12, color: '#9A3412', lineHeight: 1.45, margin: 0 }}>
                {selectedItem.whyItMatters}
              </p>
            </div>

            {/* Code Excerpt */}
            <div style={{ marginBottom: 16 }}>
              <span style={{ fontSize: 10.5, fontWeight: 800, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block', marginBottom: 4 }}>
                Code Excerpt
              </span>
              <CodeBlock
                code={selectedItem.codeExcerpt}
                filePath={selectedItem.sourcePath}
                lines={selectedItem.lines}
              />
            </div>

            {/* Related Claims */}
            {selectedItem.relatedClaims && selectedItem.relatedClaims.length > 0 && (
              <div>
                <span style={{ fontSize: 10.5, fontWeight: 800, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.6px', display: 'block', marginBottom: 6 }}>
                  Related Verification Claims
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {selectedItem.relatedClaims.map((claim) => (
                    <div 
                      key={claim.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 12px',
                        background: '#F8FAFC',
                        borderRadius: 6,
                        border: '1px solid #E2E8F0',
                        fontSize: 12
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, color: '#94A3B8', fontSize: 11 }}>{claim.id}</span>
                        <span style={{ color: '#1E293B', fontWeight: 600 }}>{claim.title}</span>
                      </div>
                      <StatusBadge status={claim.status} size="sm" />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

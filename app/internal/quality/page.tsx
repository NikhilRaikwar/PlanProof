'use client'

import React, { useState, useRef } from 'react'
import Link from 'next/link'
import {
  Activity,
  ArrowRight,
  BookOpen,
  Calendar,
  CheckCircle2,
  ChevronDown,
  Clock,
  Database,
  DollarSign,
  FileCode2,
  GitBranch,
  Info,
  Layers,
  Loader2,
  Play,
  Scale,
  ShieldCheck,
  Sparkles,
  Terminal,
  TrendingUp,
  Zap,
} from 'lucide-react'
import { MetricCard } from '@/components/metric-card'

interface ChartDataPoint {
  date: string
  fullDate: string
  accuracy: number
  recall: number
  decisionRate: number
  runs: number
  passed: number
  failed: number
  human: number
  delta: string
}

const chartData: ChartDataPoint[] = [
  {
    date: 'Apr 16',
    fullDate: 'Apr 16, 2026',
    accuracy: 78.5,
    recall: 84.0,
    decisionRate: 80.2,
    runs: 18,
    passed: 14,
    failed: 3,
    human: 1,
    delta: '+2.1% baseline'
  },
  {
    date: 'Apr 23',
    fullDate: 'Apr 23, 2026',
    accuracy: 82.0,
    recall: 86.5,
    decisionRate: 82.8,
    runs: 24,
    passed: 19,
    failed: 4,
    human: 1,
    delta: '+3.5% vs previous week'
  },
  {
    date: 'Apr 30',
    fullDate: 'Apr 30, 2026',
    accuracy: 86.4,
    recall: 89.0,
    decisionRate: 85.0,
    runs: 31,
    passed: 26,
    failed: 3,
    human: 2,
    delta: '+4.4% AST index upgrade'
  },
  {
    date: 'May 07',
    fullDate: 'May 07, 2026',
    accuracy: 89.1,
    recall: 90.2,
    decisionRate: 87.1,
    runs: 42,
    passed: 37,
    failed: 3,
    human: 2,
    delta: '+2.7% schema probe update'
  },
  {
    date: 'May 14',
    fullDate: 'May 14, 2026',
    accuracy: 90.8,
    recall: 91.5,
    decisionRate: 88.4,
    runs: 38,
    passed: 34,
    failed: 2,
    human: 2,
    delta: '+1.7% dependency check'
  },
  {
    date: 'May 16',
    fullDate: 'May 16, 2026',
    accuracy: 92.4,
    recall: 92.0,
    decisionRate: 89.0,
    runs: 49,
    passed: 45,
    failed: 2,
    human: 2,
    delta: '+1.6% current release'
  }
]

// Smooth Catmull-Rom cubic Bezier path generator passing precisely through all points
function getSplinePath(points: { x: number; y: number }[]) {
  if (points.length === 0) return ''
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`
  
  let d = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i === 0 ? 0 : i - 1]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[i + 2 >= points.length ? points.length - 1 : i + 2]

    const cp1x = p1.x + (p2.x - p0.x) * 0.16
    const cp1y = p1.y + (p2.y - p0.y) * 0.16

    const cp2x = p2.x - (p3.x - p1.x) * 0.16
    const cp2y = p2.y - (p3.y - p1.y) * 0.16

    d += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`
  }
  return d
}

export default function QualityPage() {
  const [activeSection, setActiveSection] = useState<'Overview' | 'Suites' | 'Regression' | 'CostLatency'>('Overview')
  const [selectedMetric, setSelectedMetric] = useState<'accuracy' | 'recall' | 'decisionRate'>('accuracy')
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const [isRunningAllSuites, setIsRunningAllSuites] = useState(false)
  const svgContainerRef = useRef<HTMLDivElement>(null)

  const handleRunAllSuites = () => {
    setIsRunningAllSuites(true)
    setTimeout(() => {
      setIsRunningAllSuites(false)
    }, 1500)
  }

  const evalSuites = [
    { id: 's-1', name: 'Refund assumptions', testCases: 48, passRate: 96, status: 'Passed', category: 'Behavioral', avgTime: '18s' },
    { id: 's-2', name: 'Schema contradictions', testCases: 64, passRate: 92, status: 'Passed', category: 'Data Model', avgTime: '24s' },
    { id: 's-3', name: 'Dependency impact', testCases: 72, passRate: 88, status: 'Passed', category: 'Architecture', avgTime: '31s' },
    { id: 's-4', name: 'API compatibility', testCases: 64, passRate: 84, status: 'Passed', category: 'API Contract', avgTime: '22s' }
  ]

  const regressionRuns = [
    { id: 'reg-04', commit: '8f3c1a2', date: 'May 16, 2026', total: 248, passed: 216, failed: 24, human: 8, score: '87.1%', tag: 'v1.4-rc2' },
    { id: 'reg-03', commit: 'b4e912c', date: 'May 09, 2026', total: 248, passed: 208, failed: 31, human: 9, score: '83.8%', tag: 'v1.4-rc1' },
    { id: 'reg-02', commit: '6d12a9f', date: 'May 02, 2026', total: 240, passed: 196, failed: 34, human: 10, score: '81.6%', tag: 'v1.3-prod' },
    { id: 'reg-01', commit: 'f93c011', date: 'Apr 24, 2026', total: 220, passed: 172, failed: 38, human: 10, score: '78.1%', tag: 'v1.2-prod' }
  ]

  // Chart Geometry Calculations
  const svgWidth = 760
  const svgHeight = 160
  const paddingX = 55
  const paddingTop = 25
  const paddingBottom = 40
  const chartHeight = svgHeight - paddingTop - paddingBottom
  const baselineY = paddingTop + chartHeight

  const minVal = 70
  const maxVal = 100

  const points = chartData.map((d, index) => {
    const x = paddingX + (index * (svgWidth - paddingX * 2)) / (chartData.length - 1)
    const val = d[selectedMetric]
    const ratio = (val - minVal) / (maxVal - minVal)
    const y = baselineY - ratio * chartHeight
    return { x, y, data: d, val }
  })

  const pathD = getSplinePath(points)
  const areaD = `${pathD} L ${points[points.length - 1].x.toFixed(1)} ${baselineY} L ${points[0].x.toFixed(1)} ${baselineY} Z`

  const isHovering = hoveredIndex !== null
  const activePoint = isHovering ? points[hoveredIndex] : null

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!svgContainerRef.current) return
    const rect = svgContainerRef.current.getBoundingClientRect()
    const clientX = e.clientX - rect.left
    const svgRelativeX = (clientX / rect.width) * svgWidth

    let closestIdx = 0
    let minDiff = Infinity
    points.forEach((pt, i) => {
      const diff = Math.abs(pt.x - svgRelativeX)
      if (diff < minDiff) {
        minDiff = diff
        closestIdx = i
      }
    })
    setHoveredIndex(closestIdx)
  }

  const handleMouseLeave = () => {
    setHoveredIndex(null)
  }

  const metricLabels = {
    accuracy: 'Accuracy Rate',
    recall: 'Critical Claim Recall',
    decisionRate: 'Evidence-Backed Decisions'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
        <div>
          <div className="preflight-eyebrow">
            <Sparkles size={13} />
            <span>INTERNAL ENGINEERING BENCHMARKS</span>
          </div>
          <h1 className="page-main-title" style={{ fontSize: 26 }}>Quality</h1>
          <p className="page-main-desc" style={{ margin: 0, fontSize: 13 }}>
            Measure verification reliability, regression performance, and evidence quality.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#FFFFFF', border: '1px solid #E2E8F0', padding: '6px 12px', borderRadius: 6, fontSize: 12, color: '#475569' }}>
            <Calendar size={13} />
            <span>Last 30 days</span>
            <ChevronDown size={13} style={{ color: '#94A3B8' }} />
          </div>
        </div>
      </div>

      {/* Internal Navigation Tabs */}
      <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid #E2E8F0', paddingBottom: 10 }}>
        {(['Overview', 'Suites', 'Regression', 'CostLatency'] as const).map((tab) => {
          const labels: Record<string, string> = {
            Overview: 'Overview',
            Suites: 'Evaluation suites',
            Regression: 'Regression runs',
            CostLatency: 'Cost & latency'
          }

          return (
            <button
              key={tab}
              onClick={() => setActiveSection(tab)}
              style={{
                padding: '6px 14px',
                borderRadius: 6,
                fontSize: 12.5,
                fontWeight: 750,
                border: 'none',
                cursor: 'pointer',
                background: activeSection === tab ? '#0F172A' : '#FFFFFF',
                color: activeSection === tab ? '#FFFFFF' : '#64748B',
                boxShadow: activeSection === tab ? '0 1px 3px rgba(0,0,0,0.1)' : '0 1px 2px rgba(0,0,0,0.03)',
                transition: 'all 0.15s ease'
              }}
            >
              {labels[tab]}
            </button>
          )
        })}
      </div>

      {/* SECTION 1: OVERVIEW */}
      {activeSection === 'Overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Quality Overview Card */}
          <div className="card-panel-white" style={{ padding: 22 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 850, color: '#0F172A', margin: 0 }}>System Quality Metrics</h2>
                <p style={{ fontSize: 11.5, color: '#64748B', margin: '2px 0 0' }}>Overall plan verification accuracy, claim recall, and gate precision.</p>
              </div>

              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 11,
                fontWeight: 800,
                padding: '4px 10px',
                borderRadius: 9999,
                background: '#ECFDF5',
                color: '#059669',
                border: '1px solid #A7F3D0'
              }}>
                <TrendingUp size={12} />
                <span>+6% overall quality</span>
              </span>
            </div>

            {/* 4 KPI Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 20 }}>
              <MetricCard
                label="Critical Claim Recall"
                value="0.92"
                trend="+0.04"
                trendType="positive"
                subtext="vs last month (target > 0.90)"
                hasInfo
              />
              <MetricCard
                label="Unsupported-claim Rate"
                value="0.08"
                trend="-0.02"
                trendType="positive"
                subtext="vs last month (lower is better)"
                hasInfo
              />
              <MetricCard
                label="Human Escalation Rate"
                value="0.11"
                trend="+0.01"
                trendType="neutral"
                subtext="vs last month (within target)"
                hasInfo
              />
              <MetricCard
                label="Evidence-backed Decision Rate"
                value="0.89"
                trend="+0.05"
                trendType="positive"
                subtext="vs last month (target > 0.85)"
                hasInfo
              />
            </div>

            {/* Interactive SVG Accuracy Trend Chart */}
            <div style={{
              background: '#FAFAFA',
              borderRadius: 10,
              border: '1px solid #E2E8F0',
              padding: '16px 20px',
              boxShadow: 'inset 0 1px 2px rgba(0, 0, 0, 0.02)'
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 12,
                marginBottom: 12
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                    {metricLabels[selectedMetric]}
                  </span>
                  <span style={{ fontSize: 10.5, color: '#94A3B8' }}>(Apr 16 – May 16)</span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: '#F1F5F9', padding: '2px', borderRadius: 6 }}>
                  <button
                    type="button"
                    onClick={() => setSelectedMetric('accuracy')}
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      padding: '4px 10px',
                      borderRadius: 4,
                      border: 'none',
                      cursor: 'pointer',
                      background: selectedMetric === 'accuracy' ? '#FFFFFF' : 'transparent',
                      color: selectedMetric === 'accuracy' ? '#EA580C' : '#64748B',
                      boxShadow: selectedMetric === 'accuracy' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    Accuracy ({chartData[chartData.length - 1].accuracy}%)
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedMetric('recall')}
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      padding: '4px 10px',
                      borderRadius: 4,
                      border: 'none',
                      cursor: 'pointer',
                      background: selectedMetric === 'recall' ? '#FFFFFF' : 'transparent',
                      color: selectedMetric === 'recall' ? '#EA580C' : '#64748B',
                      boxShadow: selectedMetric === 'recall' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    Recall ({chartData[chartData.length - 1].recall}%)
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedMetric('decisionRate')}
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      padding: '4px 10px',
                      borderRadius: 4,
                      border: 'none',
                      cursor: 'pointer',
                      background: selectedMetric === 'decisionRate' ? '#FFFFFF' : 'transparent',
                      color: selectedMetric === 'decisionRate' ? '#EA580C' : '#64748B',
                      boxShadow: selectedMetric === 'decisionRate' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    Decision Rate ({chartData[chartData.length - 1].decisionRate}%)
                  </button>
                </div>
              </div>

              <div
                ref={svgContainerRef}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
                style={{
                  width: '100%',
                  position: 'relative',
                  cursor: 'crosshair',
                  userSelect: 'none',
                  paddingTop: 10
                }}
              >
                <svg
                  viewBox={`0 0 ${svgWidth} ${svgHeight}`}
                  style={{
                    width: '100%',
                    height: 'auto',
                    display: 'block',
                    overflow: 'visible'
                  }}
                >
                  <defs>
                    <linearGradient id="qualityAreaGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#EA580C" stopOpacity="0.28" />
                      <stop offset="60%" stopColor="#EA580C" stopOpacity="0.08" />
                      <stop offset="100%" stopColor="#EA580C" stopOpacity="0.00" />
                    </linearGradient>

                    <filter id="glowOrangeQual" x="-20%" y="-20%" width="140%" height="140%">
                      <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#EA580C" floodOpacity="0.25" />
                    </filter>
                  </defs>

                  {[100, 90, 80, 70].map((val) => {
                    const ratio = (val - minVal) / (maxVal - minVal)
                    const y = baselineY - ratio * chartHeight
                    return (
                      <g key={val}>
                        <line
                          x1={paddingX - 10}
                          y1={y}
                          x2={svgWidth - paddingX + 10}
                          y2={y}
                          stroke="#E2E8F0"
                          strokeWidth="1"
                          strokeDasharray="3 4"
                        />
                        <text
                          x={paddingX - 18}
                          y={y + 3.5}
                          textAnchor="end"
                          fill="#94A3B8"
                          fontSize="9.5"
                          fontFamily="var(--font-mono)"
                          fontWeight="600"
                        >
                          {val}%
                        </text>
                      </g>
                    )
                  })}

                  <path d={areaD} fill="url(#qualityAreaGrad)" />

                  <path
                    d={pathD}
                    fill="none"
                    stroke="#EA580C"
                    strokeWidth="2.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    filter="url(#glowOrangeQual)"
                  />

                  {isHovering && activePoint && (
                    <g>
                      <line
                        x1={activePoint.x}
                        y1={paddingTop - 5}
                        x2={activePoint.x}
                        y2={baselineY + 4}
                        stroke="#EA580C"
                        strokeWidth="1.25"
                        strokeDasharray="3 3"
                        opacity="0.85"
                      />
                      <circle
                        cx={activePoint.x}
                        cy={baselineY}
                        r="2.5"
                        fill="#EA580C"
                      />
                    </g>
                  )}

                  {points.map((pt, idx) => {
                    const isSelected = isHovering && idx === hoveredIndex

                    return (
                      <g key={pt.data.date} style={{ transition: 'all 0.15s ease' }}>
                        {isSelected ? (
                          <>
                            <circle cx={pt.x} cy={pt.y} r="12" fill="#EA580C" fillOpacity="0.18" />
                            <circle cx={pt.x} cy={pt.y} r="7" fill="#EA580C" fillOpacity="0.3" />
                            <circle cx={pt.x} cy={pt.y} r="4.5" fill="#EA580C" stroke="#FFFFFF" strokeWidth="2.2" />
                          </>
                        ) : (
                          <circle cx={pt.x} cy={pt.y} r="3.5" fill="#EA580C" stroke="#FFFFFF" strokeWidth="1.5" />
                        )}

                        <text
                          x={pt.x}
                          y={baselineY + 20}
                          textAnchor="middle"
                          fill={isSelected ? '#0F172A' : '#64748B'}
                          fontSize="10.5"
                          fontFamily="var(--font-mono)"
                          fontWeight={isSelected ? '800' : '550'}
                        >
                          {pt.data.date}
                        </text>
                      </g>
                    )
                  })}
                </svg>

                {isHovering && activePoint && (
                  <div
                    style={{
                      position: 'absolute',
                      left: `${(activePoint.x / svgWidth) * 100}%`,
                      top: `${(activePoint.y / svgHeight) * 100}%`,
                      transform: 'translate(-50%, -125%)',
                      background: '#FFFFFF',
                      border: '1px solid #CBD5E1',
                      borderRadius: 8,
                      padding: '8px 12px',
                      boxShadow: '0 10px 25px -5px rgba(15, 23, 42, 0.14), 0 4px 6px -2px rgba(15, 23, 42, 0.05)',
                      pointerEvents: 'none',
                      zIndex: 20,
                      minWidth: 170,
                      whiteSpace: 'nowrap',
                      animation: 'fadeIn 0.12s ease'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderBottom: '1px solid #F1F5F9', paddingBottom: 5, marginBottom: 5 }}>
                      <span style={{ fontSize: 10.5, fontWeight: 750, color: '#64748B', fontFamily: 'var(--font-mono)' }}>
                        {activePoint.data.fullDate}
                      </span>
                      <span style={{ fontSize: 9.5, fontWeight: 800, color: '#059669', background: '#ECFDF5', padding: '1px 5px', borderRadius: 4 }}>
                        {activePoint.data.delta}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                      <strong style={{ fontSize: 17, fontWeight: 850, color: '#0F172A', fontFamily: 'var(--font-mono)' }}>
                        {activePoint.val}%
                      </strong>
                      <span style={{ fontSize: 10.5, color: '#475569', fontWeight: 600 }}>
                        {metricLabels[selectedMetric]}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, fontSize: 10.5, color: '#64748B', fontFamily: 'var(--font-mono)' }}>
                      <span>{activePoint.data.runs} runs</span>
                      <span>•</span>
                      <span style={{ color: '#059669', fontWeight: 700 }}>{activePoint.data.passed} passed</span>
                      <span>•</span>
                      <span style={{ color: '#DC2626', fontWeight: 700 }}>{activePoint.data.failed} disproved</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2: EVALUATION SUITES */}
      {activeSection === 'Suites' && (
        <div className="card-panel-white" style={{ padding: 22 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <h2 style={{ fontSize: 16, fontWeight: 850, color: '#0F172A', margin: 0 }}>Automated Evaluation Suites</h2>
              <span style={{ fontSize: 11.5, color: '#64748B' }}>Continuous regression tests run across verification engine versions</span>
            </div>

            <button
              onClick={handleRunAllSuites}
              disabled={isRunningAllSuites}
              className="btn-verify-plan-cta"
              style={{ padding: '7px 14px', fontSize: 12 }}
            >
              {isRunningAllSuites ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  <span>Executing suites...</span>
                </>
              ) : (
                <>
                  <Play size={13} fill="currentColor" />
                  <span>Run all suites</span>
                </>
              )}
            </button>
          </div>

          <table className="evals-table">
            <thead>
              <tr>
                <th>SUITE NAME</th>
                <th>CATEGORY</th>
                <th>TEST CASES</th>
                <th>PASS RATE</th>
                <th>AVG DURATION</th>
                <th style={{ textAlign: 'right' }}>STATUS</th>
              </tr>
            </thead>
            <tbody>
              {evalSuites.map((suite) => (
                <tr key={suite.id}>
                  <td>
                    <strong style={{ fontSize: 13, color: '#0F172A' }}>{suite.name}</strong>
                  </td>
                  <td>
                    <span style={{ fontSize: 10.5, background: '#F1F5F9', color: '#475569', padding: '2px 6px', borderRadius: 4, fontWeight: 700 }}>
                      {suite.category}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#475569' }}>
                    {suite.testCases}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <strong style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#059669' }}>{suite.passRate}%</strong>
                      <div style={{ width: 40, height: 4, background: '#E2E8F0', borderRadius: 9999, overflow: 'hidden' }}>
                        <div style={{ width: `${suite.passRate}%`, height: '100%', background: '#10B981' }} />
                      </div>
                    </div>
                  </td>
                  <td style={{ fontSize: 11.5, color: '#64748B', fontFamily: 'var(--font-mono)' }}>
                    {suite.avgTime}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10.5, fontWeight: 800, color: '#059669', background: '#ECFDF5', padding: '2px 6px', borderRadius: 4 }}>
                      <CheckCircle2 size={11} /> {suite.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* SECTION 3: REGRESSION RUNS */}
      {activeSection === 'Regression' && (
        <div className="card-panel-white" style={{ padding: 22 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <h2 style={{ fontSize: 16, fontWeight: 850, color: '#0F172A', margin: 0 }}>Regression Run History</h2>
              <span style={{ fontSize: 11.5, color: '#64748B' }}>Historical release regression test checkpoints</span>
            </div>
          </div>

          <table className="evals-table">
            <thead>
              <tr>
                <th>RUN TAG</th>
                <th>COMMIT</th>
                <th>DATE</th>
                <th>TOTAL TESTS</th>
                <th>PASSED</th>
                <th>FAILED</th>
                <th>SCORE</th>
              </tr>
            </thead>
            <tbody>
              {regressionRuns.map((r) => (
                <tr key={r.id}>
                  <td>
                    <span style={{ fontSize: 11, fontWeight: 800, background: '#FFF1EB', color: '#EA580C', border: '1px solid #FFD9CA', padding: '2px 8px', borderRadius: 4 }}>
                      {r.tag}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'var(--font-mono)', fontSize: 11.5, color: '#475569' }}>
                      <GitBranch size={12} /> {r.commit}
                    </div>
                  </td>
                  <td style={{ fontSize: 11.5, color: '#64748B' }}>{r.date}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{r.total}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#059669', fontWeight: 700 }}>{r.passed}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#DC2626', fontWeight: 700 }}>{r.failed}</td>
                  <td>
                    <strong style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: '#0F172A' }}>{r.score}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* SECTION 4: COST & LATENCY */}
      {activeSection === 'CostLatency' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
          <div className="card-panel-white" style={{ padding: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Clock size={16} style={{ color: '#EA580C' }} />
              <h3 style={{ fontSize: 14, fontWeight: 800, color: '#0F172A', margin: 0 }}>Engine Latency Telemetry</h3>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9' }}>
                <span>p50 Execution Time</span>
                <strong style={{ fontFamily: 'var(--font-mono)' }}>28.4s</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9' }}>
                <span>p95 Execution Time</span>
                <strong style={{ fontFamily: 'var(--font-mono)' }}>44.1s</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9' }}>
                <span>AST Index Cache Hit Rate</span>
                <strong style={{ fontFamily: 'var(--font-mono)', color: '#059669' }}>94.2%</strong>
              </div>
            </div>
          </div>

          <div className="card-panel-white" style={{ padding: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <DollarSign size={16} style={{ color: '#059669' }} />
              <h3 style={{ fontSize: 14, fontWeight: 800, color: '#0F172A', margin: 0 }}>Verification Run Cost Budget</h3>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9' }}>
                <span>Average Cost per Plan Verification</span>
                <strong style={{ fontFamily: 'var(--font-mono)' }}>$0.18</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9' }}>
                <span>Avg Model Tokens / Run</span>
                <strong style={{ fontFamily: 'var(--font-mono)' }}>6,420 tokens</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #F1F5F9' }}>
                <span>Infrastructure Management</span>
                <span style={{ fontWeight: 700, color: '#059669' }}>Server-side Internal</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

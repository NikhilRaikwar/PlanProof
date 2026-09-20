'use client'

import React from 'react'
import Link from 'next/link'
import { Activity, ArrowRight, Check, CheckCircle2, Copy, GitBranch, Plus, ShieldAlert, ShieldCheck } from 'lucide-react'
import { defaultRunsList } from '@/lib/data'
import { StatusBadge } from '@/components/status-badge'

export default function RunsListPage() {
  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 14 }}>
        <div>
          <div className="preflight-eyebrow">
            <Activity size={13} />
            <span>VERIFICATION RUNS</span>
          </div>
          <h1 className="page-main-title">Verification runs</h1>
          <p className="page-main-desc" style={{ margin: 0 }}>Review past verification results, coverage telemetry, and gate decisions.</p>
        </div>

        <Link 
          href="/workspace/new-verification"
          className="btn-verify-plan-cta"
          style={{ textDecoration: 'none', padding: '8px 16px', fontSize: 12.5 }}
        >
          <Plus size={15} strokeWidth={2.5} />
          <span>New verification</span>
        </Link>
      </div>

      {/* Runs Table / Cards List */}
      {defaultRunsList.length > 0 ? (
        <div className="card-panel-white" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="evals-table">
            <thead>
              <tr>
                <th style={{ padding: '12px 18px' }}>RUN</th>
                <th>CHANGE TARGET</th>
                <th>REPOSITORY & COMMIT</th>
                <th>GATE STATUS</th>
                <th>COVERAGE</th>
                <th>TIMESTAMP</th>
                <th style={{ textAlign: 'right', paddingRight: 18 }}>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {defaultRunsList.map((run) => {
                const isBlocked = run.status === 'BLOCKED'

                return (
                  <tr key={run.id} style={{ transition: 'background 0.15s ease' }}>
                    <td style={{ padding: '16px 18px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{
                          width: 28,
                          height: 28,
                          borderRadius: 6,
                          background: isBlocked ? '#FEE2E2' : '#D1FAE5',
                          color: isBlocked ? '#DC2626' : '#059669',
                          display: 'grid',
                          placeItems: 'center'
                        }}>
                          {isBlocked ? <ShieldAlert size={16} /> : <ShieldCheck size={16} />}
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, color: '#0F172A', fontSize: 12 }}>
                          {run.runNumber}
                        </span>
                      </div>
                    </td>

                    <td>
                      <strong style={{ fontSize: 13, color: '#0F172A', display: 'block' }}>{run.title}</strong>
                      <span style={{ fontSize: 11, color: '#64748B' }}>{run.claimsTotal} obligations investigated · {run.duration}</span>
                    </td>

                    <td>
                      <div style={{ fontSize: 12, color: '#1E293B', fontWeight: 600 }}>{run.repo}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10.5, color: '#64748B', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                        <span><GitBranch size={11} /> {run.branch}</span>
                        <span>•</span>
                        <span className="commit-mini-tag">{run.commit}</span>
                      </div>
                    </td>

                    <td>
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                        fontSize: 10.5,
                        fontWeight: 800,
                        padding: '2px 8px',
                        borderRadius: 4,
                        background: isBlocked ? '#FEE2E2' : '#D1FAE5',
                        color: isBlocked ? '#991B1B' : '#065F46'
                      }}>
                        {run.status}
                      </span>
                    </td>

                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <strong style={{ fontSize: 13, color: '#0F172A', fontFamily: 'var(--font-mono)' }}>{run.coverage}%</strong>
                        <div style={{ width: 50, height: 5, background: '#E2E8F0', borderRadius: 9999, overflow: 'hidden' }}>
                          <div style={{ width: `${run.coverage}%`, height: '100%', background: isBlocked ? '#EA580C' : '#10B981' }} />
                        </div>
                      </div>
                    </td>

                    <td style={{ fontSize: 11.5, color: '#64748B' }}>{run.timestamp}</td>

                    <td style={{ textAlign: 'right', paddingRight: 18 }}>
                      <Link
                        href={`/workspace/runs/${run.id}`}
                        className="btn-plan-action"
                        style={{ textDecoration: 'none', display: 'inline-flex' }}
                      >
                        <span>View report</span>
                        <ArrowRight size={12} />
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card-panel-white" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: '#FFF1EB', color: '#EA580C', display: 'grid', placeItems: 'center', margin: '0 auto 16px' }}>
            <Activity size={24} />
          </div>
          <h2 style={{ fontSize: 18, fontWeight: 800, color: '#0F172A', margin: '0 0 6px' }}>No verification runs yet</h2>
          <p style={{ fontSize: 13, color: '#64748B', maxWidth: 420, margin: '0 auto 20px' }}>
            Verify your first engineering plan against your codebase to gate risky assumptions before implementation.
          </p>
          <Link
            href="/workspace/new-verification"
            className="btn-verify-plan-cta"
            style={{ textDecoration: 'none', display: 'inline-flex', padding: '8px 18px', fontSize: 12.5 }}
          >
            <Plus size={14} />
            <span>Verify your first plan</span>
          </Link>
        </div>
      )}
    </div>
  )
}

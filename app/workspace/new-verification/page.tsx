'use client'

import React, { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { 
  ArrowRight, 
  Check, 
  FileCode2, 
  FileText, 
  GitBranch, 
  GitCommit, 
  Layers3, 
  Loader2, 
  ShieldCheck, 
  Upload 
} from 'lucide-react'
import { api, ApiError, Project, Snapshot } from '@/lib/api'
import { useWorkspace } from '@/components/workspace-context'

type SnapshotRow = {
  project: Project
  snapshot: Snapshot
}

export default function NewVerificationPage() {
  const router = useRouter()
  const { selectedRepo, selectRepository } = useWorkspace()
  const [rows, setRows] = useState<SnapshotRow[]>([])
  const [selectedSnapshotId, setSelectedSnapshotId] = useState('')
  const [changeRequest, setChangeRequest] = useState('')
  const [candidatePlan, setCandidatePlan] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    void (async () => {
      try {
        const ps = await api.workspaceProjects().catch(() => api.projects().catch(() => []))
        const pairs: SnapshotRow[] = []

        await Promise.all(
          ps.map(async project => {
            try {
              const snaps = await api.snapshots(project.id)
              snaps.forEach(snap => {
                if (snap.status === 'READY') {
                  pairs.push({ project, snapshot: snap })
                }
              })
            } catch {
              // Ignore single project fetch error
            }
          })
        )

        setRows(pairs)

        const urlParamSnapshotId =
          typeof window !== 'undefined'
            ? new URLSearchParams(window.location.search).get('snapshot_id')
            : null
        const targetId = urlParamSnapshotId || selectedRepo?.snapshotId

        let chosen = pairs.find(p => p.snapshot.id === targetId)
        if (!chosen && selectedRepo?.repositoryId) {
          chosen = pairs.find(p => p.project.id === selectedRepo.repositoryId)
        }
        if (!chosen && pairs.length > 0) {
          chosen = pairs[0]
        }
        if (chosen) {
          setSelectedSnapshotId(chosen.snapshot.id)
          selectRepository(chosen.project, chosen.snapshot)
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not load repository snapshots.')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    const row = rows.find(x => x.snapshot.id === selectedSnapshotId)
    if (!row) {
      setError('Please select a READY repository snapshot.')
      return
    }
    if (!changeRequest.trim()) {
      setError('Please describe the intended software change.')
      return
    }
    if (!candidatePlan.trim()) {
      setError('Please paste or upload a candidate engineering plan.')
      return
    }

    setSubmitting(true)
    try {
      const version = await api.createPlan(row.project.id, {
        change_request: changeRequest,
        candidate_plan: candidatePlan
      })
      const run = await api.createRun({
        project_id: row.project.id,
        snapshot_id: row.snapshot.id,
        plan_version_id: version.id
      })
      router.push(`/workspace/runs/${run.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not queue verification run.')
      setSubmitting(false)
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      file.text().then(text => setCandidatePlan(text))
    }
  }

  const selectedRow = rows.find(x => x.snapshot.id === selectedSnapshotId)

  return (
    <div style={{ display: 'grid', gap: 24 }}>
      {/* Page Header */}
      <div>
        <div className="preflight-eyebrow">
          <FileText size={13} />
          <span>PRE-FLIGHT VERIFICATION INTAKE</span>
        </div>
        <h1 className="page-main-title">Verify an engineering plan</h1>
        <p className="page-main-desc">
          PlanProof extracts claims from candidate plans and checks them against repository code evidence.
        </p>
      </div>

      {loading ? (
        <div className="card-panel-white" style={{ textAlign: 'center', padding: 48, color: '#64748B' }}>
          Loading repository snapshots…
        </div>
      ) : rows.length === 0 ? (
        /* Polished Empty State when no READY snapshot exists */
        <div className="card-panel-white" style={{ textAlign: 'center', padding: '56px 24px' }}>
          <div style={{ width: 52, height: 52, borderRadius: 14, background: '#FFF1EB', color: '#EA580C', display: 'grid', placeItems: 'center', margin: '0 auto 16px' }}>
            <Layers3 size={28} />
          </div>
          <h2 style={{ fontSize: 18, fontWeight: 750, color: '#0F172A', marginBottom: 6 }}>
            No READY repository snapshot yet
          </h2>
          <p style={{ color: '#64748B', fontSize: 13, maxWidth: 460, margin: '0 auto 24px', lineHeight: 1.5 }}>
            PlanProof requires an indexed repository snapshot to verify proof obligations against codebase evidence. Select a repository to create and index a snapshot.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 12 }}>
            <Link 
              href="/workspace/repositories" 
              className="btn-verify-plan-cta"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}
            >
              <Layers3 size={15} />
              <span>Select repository</span>
            </Link>
          </div>
        </div>
      ) : (
        /* Verification Intake Form Grid */
        <div className="dashboard-two-col-grid">
          <form onSubmit={handleStart} className="card-panel-white" style={{ display: 'grid', gap: 18 }}>
            {/* Target Snapshot Selection */}
            <div className="form-field-block">
              <label className="form-field-label" htmlFor="target-snapshot">
                Target READY snapshot
              </label>
              <select
                id="target-snapshot"
                className="custom-select-box"
                value={selectedSnapshotId}
                onChange={e => {
                  const newId = e.target.value
                  setSelectedSnapshotId(newId)
                  const found = rows.find(r => r.snapshot.id === newId)
                  if (found) {
                    selectRepository(found.project, found.snapshot)
                  }
                }}
              >
                {rows.map(({ project, snapshot }) => {
                  const isDemo = project.repository_source_type === 'seeded_fixture'
                  const shortSha = snapshot.resolved_commit_sha ? snapshot.resolved_commit_sha.slice(0, 7) : 'HEAD'
                  const refName = snapshot.requested_ref || project.requested_ref || 'main'
                  return (
                    <option key={snapshot.id} value={snapshot.id}>
                      {isDemo ? 'Demo fixture — ' : ''}{project.name} · {refName} ({shortSha})
                    </option>
                  )
                })}
              </select>

              {selectedRow && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, fontSize: 11.5, color: '#64748B' }}>
                  <span className="badge-pill-base badge-verified" style={{ fontSize: 10 }}>
                    <span className="synced-green-dot" />
                    READY
                  </span>
                  <span>{selectedRow.snapshot.files_indexed ?? 0} files indexed</span>
                  <span>·</span>
                  <span>{selectedRow.snapshot.symbols_indexed ?? 0} symbols</span>
                  {selectedRow.snapshot.resolved_commit_sha && (
                    <span className="commit-mini-tag">
                      <GitCommit size={10} style={{ marginRight: 2 }} />
                      {selectedRow.snapshot.resolved_commit_sha.slice(0, 7)}
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Change Request Description */}
            <div className="form-field-block">
              <label className="form-field-label" htmlFor="change-request">
                What are you planning to change?
              </label>
              <input
                id="change-request"
                className="custom-text-input"
                value={changeRequest}
                maxLength={20000}
                onChange={e => setChangeRequest(e.target.value)}
                placeholder="e.g. Add idempotency keys to payment refund webhook handler"
              />
            </div>

            {/* Candidate Plan Input */}
            <div className="form-field-block">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <label className="form-field-label" htmlFor="candidate-plan" style={{ margin: 0 }}>
                  Candidate engineering plan
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".md,.txt,.json,.yaml,.yml"
                  hidden
                  onChange={handleFileUpload}
                />
                <button
                  type="button"
                  className="btn-plan-action"
                  onClick={() => fileInputRef.current?.click()}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11.5 }}
                >
                  <Upload size={12} />
                  <span>Upload plan file</span>
                </button>
              </div>

              <textarea
                id="candidate-plan"
                className="custom-textarea"
                rows={11}
                value={candidatePlan}
                maxLength={50000}
                onChange={e => setCandidatePlan(e.target.value)}
                placeholder={`Paste candidate engineering plan (Markdown, text, YAML, or JSON)...

Example plan statements:
- Store refund idempotency keys in Redis with a 24-hour TTL
- Add unique constraint on (account_id, idempotency_key) in database
- Check payment-gateway API contracts for error responses`}
              />
            </div>

            {error && (
              <div style={{ padding: '10px 14px', borderRadius: 8, background: '#FEF2F2', border: '1px solid #FCA5A5', color: '#B91C1C', fontSize: 12.5 }}>
                {error}
              </div>
            )}

            <div>
              <button
                type="submit"
                className="btn-verify-plan-cta"
                disabled={submitting}
                style={{ width: '100%', justifyContent: 'center', padding: '11px 20px', fontSize: 13.5 }}
              >
                {submitting ? (
                  <>
                    <Loader2 size={15} className="animate-spin" />
                    <span>Queueing verification…</span>
                  </>
                ) : (
                  <>
                    <span>Verify this plan</span>
                    <ArrowRight size={15} />
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Right Column: Workflow Context & Guidance */}
          <div className="right-stack-col" style={{ display: 'grid', gap: 16 }}>
            <div className="what-next-card">
              <h3 className="card-heading-compact" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <ShieldCheck size={16} color="#EA580C" />
                <span>Verification Pipeline</span>
              </h3>
              
              <div style={{ display: 'grid', gap: 12, marginTop: 12, fontSize: 12.5, color: '#475569' }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <span style={{ width: 22, height: 22, borderRadius: 6, background: '#FFF1EB', color: '#EA580C', fontWeight: 800, display: 'grid', placeItems: 'center', flexShrink: 0, fontSize: 11 }}>1</span>
                  <div>
                    <strong style={{ color: '#0F172A', display: 'block' }}>Extract proof obligations</strong>
                    <span>Candidate plan statements are parsed into testable claims across behavior, schema, and API contracts.</span>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <span style={{ width: 22, height: 22, borderRadius: 6, background: '#FFF1EB', color: '#EA580C', fontWeight: 800, display: 'grid', placeItems: 'center', flexShrink: 0, fontSize: 11 }}>2</span>
                  <div>
                    <strong style={{ color: '#0F172A', display: 'block' }}>Gather deterministic evidence</strong>
                    <span>Bounded AST tools search repository files, line ranges, symbols, and schema definitions.</span>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <span style={{ width: 22, height: 22, borderRadius: 6, background: '#FFF1EB', color: '#EA580C', fontWeight: 800, display: 'grid', placeItems: 'center', flexShrink: 0, fontSize: 11 }}>3</span>
                  <div>
                    <strong style={{ color: '#0F172A', display: 'block' }}>Server-authoritative Plan Gate</strong>
                    <span>Returns an immutable gate decision (<code>VERIFIED</code> or <code>BLOCKED</code>) before agents or engineers write code.</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="card-panel-subtle" style={{ padding: 16, fontSize: 12, color: '#64748B' }}>
              <strong style={{ color: '#0F172A', display: 'block', marginBottom: 4 }}>Human-in-the-loop escalation</strong>
              <span>If a plan claim requires business authority that cannot be proven from code alone, PlanProof halts in <code>HUMAN_WAIT</code> and asks for authorized confirmation.</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

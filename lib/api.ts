export type ApiStatus = 'READY' | 'QUEUED' | 'VERIFYING' | 'HUMAN_WAIT' | 'BLOCKED' | 'COMPLETE' | 'INCONCLUSIVE' | 'FAILED' | string

export type Project = { id: string; name: string; repository_source_type: 'public_github' | 'seeded_fixture'; repository_url?: string | null; fixture_id?: string | null; requested_ref?: string | null; created_at: string }
export type Snapshot = { id: string; project_id: string; repository_identity: string; source_type: string; requested_ref?: string | null; resolved_commit_sha?: string | null; status: ApiStatus; files_indexed: number; symbols_indexed: number; ignored_files: number; supported_languages: string[]; created_at: string; updated_at: string }
export type PlanVersion = { id: string; project_id: string; version: number; change_request: string; candidate_plan: string; parent_plan_version_id?: string | null; created_at: string }
export type VerificationRun = { id: string; project_id: string; snapshot_id: string; plan_version_id: string; status: ApiStatus; created_at: string; updated_at: string }
export type Obligation = { id: string; statement: string; category: string; criticality: string; status: string; evidence_ids: string[]; counter_evidence_ids: string[] }
export type Evidence = { id: string; snapshot_id: string; source_tool_run_id: string; evidence_type: string; path?: string | null; start_line?: number | null; end_line?: number | null; content_hash?: string | null; safe_fact_summary: string; created_at: string }
export type ToolRun = { id: string; tool_name: string; status: string; input_hash: string; result_count: number; safe_error_class?: string | null; duration_ms: number; started_at: string; finished_at?: string | null }
export type HumanQuestion = { id: string; obligation_id: string; question: string; why_needed: string; authority_required: string; status: string }
export type RunProjection = { run: VerificationRun; obligation_counts: Record<string, number>; human_questions: HumanQuestion[]; tool_runs: ToolRun[]; evidence_count: number }

export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }
const base = (process.env.NEXT_PUBLIC_PLANPROOF_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(`${base}/v1${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } }) }
  catch { throw new ApiError(0, 'PlanProof backend is unavailable.') }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(response.status, payload?.detail || 'The request could not be completed.')
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => fetch(`${base}/health/ready`).then(r => r.ok),
  projects: () => request<Project[]>('/projects'),
  createProject: (body: object) => request<Project>('/projects', { method: 'POST', body: JSON.stringify(body) }),
  snapshots: (projectId: string) => request<Snapshot[]>(`/projects/${projectId}/snapshots`),
  createSnapshot: (projectId: string) => request<Snapshot>(`/projects/${projectId}/snapshots`, { method: 'POST' }),
  createPlan: (projectId: string, body: object) => request<PlanVersion>(`/projects/${projectId}/plan-versions`, { method: 'POST', body: JSON.stringify(body) }),
  createRun: (body: object) => request<VerificationRun>('/verification-runs', { method: 'POST', body: JSON.stringify(body) }),
  runs: () => request<VerificationRun[]>('/verification-runs'),
  run: (id: string) => request<RunProjection>(`/verification-runs/${id}`),
  obligations: (id: string) => request<Obligation[]>(`/verification-runs/${id}/proof-obligations`),
  evidence: (id: string) => request<Evidence[]>(`/verification-runs/${id}/evidence`),
  toolRuns: (id: string) => request<ToolRun[]>(`/verification-runs/${id}/tool-runs`),
  answer: (id: string, answer: string) => request<HumanQuestion>(`/human-questions/${id}/answers`, { method: 'POST', body: JSON.stringify({ answer, actor_id: 'local-session' }) }),
  amend: (id: string, candidate_plan: string) => request<PlanVersion>(`/plan-versions/${id}/amendments`, { method: 'POST', body: JSON.stringify({ candidate_plan }) }),
  eventsUrl: (id: string) => `${base}/v1/verification-runs/${id}/events`,
}

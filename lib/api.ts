export type ApiStatus = 'READY' | 'QUEUED' | 'VERIFYING' | 'HUMAN_WAIT' | 'BLOCKED' | 'COMPLETE' | 'INCONCLUSIVE' | 'FAILED' | string

export type Project = {
  id: string
  name: string
  owner_id: string
  repository_source_type: 'public_github' | 'seeded_fixture' | 'github_app'
  repository_url?: string | null
  fixture_id?: string | null
  requested_ref?: string | null
  github_repository_id?: number | null
  github_installation_id?: number | null
  data_scope?: 'USER' | 'DEMO' | string
  created_at: string
}

export type Snapshot = {
  id: string
  project_id: string
  repository_identity: string
  source_type: string
  requested_ref?: string | null
  resolved_commit_sha?: string | null
  status: ApiStatus
  files_indexed: number
  symbols_indexed: number
  ignored_files: number
  supported_languages: string[]
  created_at: string
  updated_at: string
}

export type PlanVersion = {
  id: string
  project_id: string
  version: number
  change_request: string
  candidate_plan: string
  parent_plan_version_id?: string | null
  created_at: string
}

export type VerificationRun = {
  id: string
  project_id: string
  snapshot_id: string
  plan_version_id: string
  status: ApiStatus
  created_at: string
  updated_at: string
  tool_call_count: number
  model_call_count: number
  prompt_tokens: number
  completion_tokens: number
  estimated_cost_usd: number
  commit_sha?: string | null
  ref?: string | null
  plan_title?: string | null
  evidence_count?: number | null
  tool_execution_count?: number | null
  has_open_human_question?: boolean | null
}

export type Obligation = {
  id: string
  statement: string
  category: string
  criticality: string
  status: string
  semantic_role?: string
  evidence_ids: string[]
  counter_evidence_ids: string[]
  verification_hints?: string[]
  proposal_metadata?: Record<string, string>
}

export type Evidence = {
  id: string
  snapshot_id: string
  source_tool_run_id: string
  evidence_type: string
  path?: string | null
  start_line?: number | null
  end_line?: number | null
  line_start?: number | null
  line_end?: number | null
  content_hash?: string | null
  summary?: string
  safe_fact_summary: string
  snippet?: string | null
  obligation_id?: string | null
  obligation_statement?: string | null
  relationship?: 'SUPPORTS' | 'CONTRADICTS' | null
  created_at: string
}

export type ToolRun = {
  id: string
  snapshot_id?: string
  run_id?: string | null
  tool_name: string
  status: string
  input_hash: string
  input_summary?: Record<string, any> | null
  result_count: number
  safe_error_class?: string | null
  duration_ms: number
  started_at: string
  finished_at?: string | null
}

export type HumanQuestion = {
  id: string
  obligation_id: string
  question: string
  why_needed: string
  authority_required: string
  status: string
  answer?: string | null
  actor_id?: string | null
  answered_at?: string | null
}

export type RunRepositoryContext = {
  id: string
  name: string
  full_name?: string | null
  repository_source_type: string
}

export type RunSnapshotContext = {
  id: string
  requested_ref?: string | null
  resolved_commit_sha?: string | null
  status: string
}

export type RunPlanContext = {
  id: string
  version: number
  change_request: string
}

export type PlanChange = {
  id: string
  change_type: 'KEEP' | 'MODIFY' | 'REMOVE' | 'ADD' | 'UNRESOLVED'
  source_plan_step_ids: string[]
  original_text?: string | null
  updated_text?: string | null
  rationale: string
  basis_fact_ids: string[]
  evidence_ids: string[]
  human_decision_ids: string[]
}

export type RevisedPlanStep = {
  id: string
  order: number
  action: string
  rationale: string
  status: 'KEEP' | 'MODIFY' | 'REMOVE' | 'ADD' | 'UNRESOLVED'
  source_plan_step_ids: string[]
  basis_fact_ids: string[]
  supporting_obligation_ids: string[]
  supporting_evidence_ids: string[]
  supporting_human_decision_ids: string[]
  unresolved_dependency_ids: string[]
  existing_target_files: string[]
  proposed_new_files: string[]
  existing_target_symbols?: string[]
  proposed_new_symbols?: string[]
  target_symbols: string[]
  confidence_basis: 'EVIDENCE_BACKED' | 'PARTIALLY_EVIDENCED' | 'HUMAN_CONFIRMED' | 'UNRESOLVED'
}

export type RevisedPlan = {
  id: string
  run_id: string
  project_id: string
  snapshot_id: string
  original_plan_version_id: string
  revision_version: number
  status: 'EVIDENCE_GROUNDED' | 'PROVISIONAL' | 'AWAITING_HUMAN_DECISION' | 'UNAVAILABLE'
  executive_summary: string
  plan_changes: PlanChange[]
  implementation_plan: RevisedPlanStep[]
  model_call_id?: string | null
  created_at: string
}

export type RunProjection = {
  run: VerificationRun
  repository?: RunRepositoryContext
  snapshot?: RunSnapshotContext
  plan?: RunPlanContext
  obligation_counts: Record<string, number>
  human_questions: HumanQuestion[]
  tool_runs: ToolRun[]
  evidence_count: number
  tool_execution_count?: number
  trace_attribution_status?: string
}

export type EvaluationRun = { eval_run_id: string; timestamp: string; sample_count: number; metrics: Record<string, number>; limitations: string[] }
export type Session = { connected: true; account_login: string; installation_id: number; session_token?: string }
export type GitHubRepository = { id: number; owner: string; name: string; full_name: string; private: boolean; default_branch: string }
export type GitHubRef = { name: string; commit_sha: string }

export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }

const SESSION_STORAGE_KEY = 'planproof_session_token'

export function getStoredSessionToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem(SESSION_STORAGE_KEY)
  }
  return null
}

export function setStoredSessionToken(token: string | null) {
  if (typeof window !== 'undefined') {
    if (token) {
      localStorage.setItem(SESSION_STORAGE_KEY, token)
    } else {
      localStorage.removeItem(SESSION_STORAGE_KEY)
    }
  }
}

function getBaseUrl(): string {
  if (typeof window !== 'undefined') {
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      return ''
    }
    return (process.env.NEXT_PUBLIC_PLANPROOF_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
  }
  return (process.env.PLANPROOF_API_URL || process.env.NEXT_PUBLIC_PLANPROOF_API_URL || '').replace(/\/$/, '')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getBaseUrl()
  const token = getStoredSessionToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init?.headers as Record<string, string> || {}),
  }

  let response: Response
  try { response = await fetch(`${base}/v1${path}`, { ...init, credentials: 'include', headers }) }
  catch { throw new ApiError(0, 'PlanProof backend is unavailable.') }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(response.status, payload?.detail || 'The request could not be completed.')
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => {
    const base = getBaseUrl()
    return fetch(`${base}/health/ready`).then(r => r.ok)
  },
  projects: () => request<Project[]>('/projects'),
  workspaceProjects: (includeDemo = false) => request<Project[]>(`/workspace/projects${includeDemo ? '?include_demo=true' : ''}`),
  session: () => request<Session>('/auth/session'),
  claimSession: async (sessionToken: string) => {
    setStoredSessionToken(sessionToken)
    try {
      const sess = await request<Session>('/auth/session/claim', { method: 'POST', body: JSON.stringify({ session_token: sessionToken }) })
      if (sess?.session_token) {
        setStoredSessionToken(sess.session_token)
      }
      return sess
    } catch (err) {
      setStoredSessionToken(null)
      throw err
    }
  },
  logout: async () => {
    setStoredSessionToken(null)
    return request<{ connected: false }>('/auth/logout', { method: 'POST' })
  },
  connectGithubUrl: () => {
    const base = getBaseUrl()
    return `${base}/v1/auth/github/connect`
  },
  githubRepositories: () => request<GitHubRepository[]>('/github/repositories'),
  githubRefs: (repositoryId: number) => request<GitHubRef[]>(`/github/repositories/${repositoryId}/refs`),
  createConnectedSnapshot: (repositoryId: number, requested_ref?: string) => request<Snapshot>(`/github/repositories/${repositoryId}/snapshots`, { method: 'POST', body: JSON.stringify({ requested_ref }) }),
  createDemoSnapshot: () => request<Snapshot>('/workspace/demo-snapshot', { method: 'POST' }),
  createProject: (body: object) => request<Project>('/projects', { method: 'POST', body: JSON.stringify(body) }),
  snapshots: (projectId: string) => request<Snapshot[]>(`/projects/${projectId}/snapshots`),
  createSnapshot: (projectId: string) => request<Snapshot>(`/projects/${projectId}/snapshots`, { method: 'POST' }),
  createPlan: (projectId: string, body: object) => request<PlanVersion>(`/projects/${projectId}/plan-versions`, { method: 'POST', body: JSON.stringify(body) }),
  createRun: (body: object) => request<VerificationRun>('/verification-runs', { method: 'POST', body: JSON.stringify(body) }),
  runs: (projectId?: string) => request<VerificationRun[]>(`/verification-runs${projectId ? `?project_id=${projectId}` : ''}`),
  run: (id: string) => request<RunProjection>(`/verification-runs/${id}`),
  obligations: (id: string) => request<Obligation[]>(`/verification-runs/${id}/proof-obligations`),
  evidence: (id: string) => request<Evidence[]>(`/verification-runs/${id}/evidence`),
  toolRuns: (id: string) => request<ToolRun[]>(`/verification-runs/${id}/tool-runs`),
  answer: (id: string, answer: string) => request<HumanQuestion>(`/human-questions/${id}/answers`, { method: 'POST', body: JSON.stringify({ answer, actor_id: 'local-session' }) }),
  amend: (id: string, candidate_plan: string) => request<PlanVersion>(`/plan-versions/${id}/amendments`, { method: 'POST', body: JSON.stringify({ candidate_plan }) }),
  revisedPlan: (runId: string) => request<RevisedPlan | null>(`/verification-runs/${runId}/revised-plan`),
  revisedPlans: (runId: string) => request<RevisedPlan[]>(`/verification-runs/${runId}/revised-plans`),
  latestEvaluation: () => request<EvaluationRun>('/evaluations/latest'),
  eventsUrl: (id: string) => `${getBaseUrl()}/v1/verification-runs/${id}/events`,
}

'use client'

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { api, Project, Snapshot, Session } from '@/lib/api'

export interface CanonicalWorkspaceContext {
  repositoryId: string
  repositoryFullName: string
  ref?: string
  snapshotId?: string
  commitSha?: string
  snapshotStatus?: string
  githubRepositoryId?: number | null
  githubInstallationId?: number | null
  dataScope?: 'USER' | 'DEMO' | string
  isRunContext?: boolean
}

interface WorkspaceContextType {
  session: Session | null
  selectedRepo: CanonicalWorkspaceContext | null
  runContext: CanonicalWorkspaceContext | null
  activeContext: CanonicalWorkspaceContext | null
  userProjects: Project[]
  loading: boolean
  error: string | null
  selectRepository: (project: Project, snapshot?: Snapshot | null) => void
  setRunContext: (ctx: CanonicalWorkspaceContext | null) => void
  refreshProjects: () => Promise<void>
}

const WorkspaceContext = createContext<WorkspaceContextType | null>(null)

function getStorageKey(installationId: number): string {
  return `planproof:workspace-context:${installationId}`
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [selectedRepo, setSelectedRepo] = useState<CanonicalWorkspaceContext | null>(null)
  const [runContext, setRunContextState] = useState<CanonicalWorkspaceContext | null>(null)
  const [userProjects, setUserProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadWorkspace = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const sess = await api.session().catch(() => null)
      setSession(sess)

      if (!sess?.installation_id) {
        setSelectedRepo(null)
        setUserProjects([])
        setLoading(false)
        return
      }

      // 1. Fetch user projects (DEMO is excluded by backend default)
      const projects = await api.workspaceProjects(false).catch(() => [])
      // Double check: ensure no demo fixtures leak into normal workspace
      const verifiedProjects = projects.filter(
        p => p.data_scope !== 'DEMO' && !p.name.startsWith('e2e-')
      )
      setUserProjects(verifiedProjects)

      // 2. Read tenant-scoped persisted context from localStorage
      const storageKey = getStorageKey(sess.installation_id)
      const rawPersisted = typeof window !== 'undefined' ? localStorage.getItem(storageKey) : null

      if (rawPersisted) {
        try {
          const parsed = JSON.parse(rawPersisted) as CanonicalWorkspaceContext
          // Validate against authenticated user projects
          const matchedProject = verifiedProjects.find(p => p.id === parsed.repositoryId)

          if (matchedProject) {
            // Verify exact snapshot validity without silently advancing to latest
            let validSnapshot: Snapshot | null = null
            if (parsed.snapshotId) {
              try {
                const snaps = await api.snapshots(matchedProject.id)
                const found = snaps.find(s => s.id === parsed.snapshotId && s.status === 'READY')
                if (found) {
                  validSnapshot = found
                }
              } catch {
                // Ignore single snapshot fetch error
              }
            }

            if (validSnapshot) {
              setSelectedRepo({
                repositoryId: matchedProject.id,
                repositoryFullName: matchedProject.name,
                ref: validSnapshot.requested_ref || matchedProject.requested_ref || 'main',
                snapshotId: validSnapshot.id,
                commitSha: validSnapshot.resolved_commit_sha || undefined,
                snapshotStatus: validSnapshot.status,
                githubRepositoryId: matchedProject.github_repository_id,
                githubInstallationId: matchedProject.github_installation_id,
                dataScope: matchedProject.data_scope || 'USER',
              })
            } else {
              // Exact snapshot is no longer valid/ready. Keep repository selection but clear snapshot!
              setSelectedRepo({
                repositoryId: matchedProject.id,
                repositoryFullName: matchedProject.name,
                ref: matchedProject.requested_ref || 'main',
                githubRepositoryId: matchedProject.github_repository_id,
                githubInstallationId: matchedProject.github_installation_id,
                dataScope: matchedProject.data_scope || 'USER',
              })
            }
          } else {
            // Persisted repository no longer belongs to this installation
            localStorage.removeItem(storageKey)
            setSelectedRepo(null)
          }
        } catch {
          localStorage.removeItem(storageKey)
          setSelectedRepo(null)
        }
      } else if (verifiedProjects.length === 1) {
        // Automatically select if only one authenticated repository exists
        const single = verifiedProjects[0]
        let singleSnap: Snapshot | null = null
        try {
          const snaps = await api.snapshots(single.id)
          singleSnap = snaps.find(s => s.status === 'READY') || snaps[0] || null
        } catch {
          // Ignore single snapshot error
        }

        setSelectedRepo({
          repositoryId: single.id,
          repositoryFullName: single.name,
          ref: singleSnap?.requested_ref || single.requested_ref || 'main',
          snapshotId: singleSnap?.id,
          commitSha: singleSnap?.resolved_commit_sha || undefined,
          snapshotStatus: singleSnap?.status,
          githubRepositoryId: single.github_repository_id,
          githubInstallationId: single.github_installation_id,
          dataScope: single.data_scope || 'USER',
        })
      } else {
        setSelectedRepo(null)
      }
    } catch (e: any) {
      setError(e?.message || 'Could not load workspace')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadWorkspace()
  }, [loadWorkspace])

  const selectRepository = useCallback(
    (project: Project, snapshot?: Snapshot | null) => {
      const newContext: CanonicalWorkspaceContext = {
        repositoryId: project.id,
        repositoryFullName: project.name,
        ref: snapshot?.requested_ref || project.requested_ref || 'main',
        snapshotId: snapshot?.id,
        commitSha: snapshot?.resolved_commit_sha || undefined,
        snapshotStatus: snapshot?.status,
        githubRepositoryId: project.github_repository_id,
        githubInstallationId: project.github_installation_id,
        dataScope: project.data_scope || 'USER',
      }

      setSelectedRepo(newContext)

      if (session?.installation_id && typeof window !== 'undefined') {
        const storageKey = getStorageKey(session.installation_id)
        localStorage.setItem(storageKey, JSON.stringify(newContext))
      }
    },
    [session]
  )

  const setRunContext = useCallback((ctx: CanonicalWorkspaceContext | null) => {
    setRunContextState(ctx)
  }, [])

  // Run context takes priority for the topbar while viewing a Run Report,
  // but NEVER overwrites the persistent selectedRepo
  const activeContext = runContext || selectedRepo

  return (
    <WorkspaceContext.Provider
      value={{
        session,
        selectedRepo,
        runContext,
        activeContext,
        userProjects,
        loading,
        error,
        selectRepository,
        setRunContext,
        refreshProjects: loadWorkspace,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext)
  if (!context) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider')
  }
  return context
}

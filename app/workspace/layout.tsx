import React from 'react'
import type { Metadata } from 'next'
import { WorkspaceShell } from '@/components/workspace-shell'

export const metadata: Metadata = {
  title: 'Workspace',
  robots: {
    index: false,
    follow: false,
    nocache: true,
  },
}

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <WorkspaceShell>{children}</WorkspaceShell>
}

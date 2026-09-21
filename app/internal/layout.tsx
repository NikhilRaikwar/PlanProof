import React from 'react'
import type { Metadata } from 'next'
import { InternalShell } from '@/components/internal-shell'

export const metadata: Metadata = {
  title: 'Internal Quality Benchmarks',
  robots: {
    index: false,
    follow: false,
    nocache: true,
  },
}

export default function InternalLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <InternalShell>{children}</InternalShell>
}

import React from 'react'

export function StructuredData() {
  const siteUrl =
    process.env.NEXT_PUBLIC_SITE_URL || 'https://planproof.nikhilraikwar.me'

  const softwareAppSchema = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'PlanProof',
    applicationCategory: 'DeveloperApplication',
    operatingSystem: 'Web',
    description:
      'Pre-flight verification system for AI-generated software engineering plans. PlanProof binds candidate plans to immutable repository snapshots, extracts testable proof obligations, gathers code-backed evidence, and computes deterministic Plan Gates before agents build.',
    url: siteUrl,
    image: `${siteUrl}/banner.png`,
    softwareVersion: '0.1.0',
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'USD',
    },
    author: {
      '@type': 'Person',
      name: 'Nikhil Raikwar',
      url: 'https://github.com/NikhilRaikwar',
    },
    featureList: [
      'Pre-flight engineering plan verification',
      'Immutable repository snapshots with Git SHA binding',
      'Cryptographic server-issued evidence authority',
      'Deterministic AST parsing and lexical search tools',
      'Bounded LangGraph agent state machine orchestration',
      'Human-in-the-loop (HITL) authority pause and resumption',
      'Provider fallback resilience (OpenRouter to AIMLAPI)',
      '27-case versioned evaluation harness',
    ],
  }

  const websiteSchema = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'PlanProof',
    url: siteUrl,
    description: 'Pre-flight verification for AI-generated engineering plans.',
    publisher: {
      '@type': 'Organization',
      name: 'PlanProof',
      logo: {
        '@type': 'ImageObject',
        url: `${siteUrl}/logo.png`,
      },
    },
  }

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareAppSchema) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteSchema) }}
      />
    </>
  )
}

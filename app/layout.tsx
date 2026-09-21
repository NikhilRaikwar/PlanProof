import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import './globals.css'

const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL || 'https://planproof-web-lfrrer4z6q-el.a.run.app'

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: 'PlanProof — Verify Engineering Plans Before Agents Build',
    template: '%s | PlanProof',
  },
  description:
    'PlanProof verifies AI-generated engineering plans against real codebase snapshots using deterministic evidence, bounded agent workflows, human-in-the-loop decisions, and production-grade evals.',
  applicationName: 'PlanProof',
  authors: [{ name: 'Nikhil Raikwar', url: 'https://github.com/NikhilRaikwar' }],
  creator: 'Nikhil Raikwar',
  publisher: 'PlanProof',
  category: 'Developer Tools',
  alternates: {
    canonical: '/',
  },
  openGraph: {
    type: 'website',
    siteName: 'PlanProof',
    title: 'PlanProof — Verify Engineering Plans Before Agents Build',
    description:
      'Verify the plan before agents build it. PlanProof checks AI-generated engineering plans against real repository evidence before implementation starts.',
    url: '/',
    locale: 'en_US',
    images: [
      {
        url: '/banner.png',
        width: 1200,
        height: 630,
        alt: 'PlanProof — Verify the plan before agents build it.',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'PlanProof — Verify the plan before agents build it.',
    description:
      'Evidence-grounded verification for AI engineering plans before implementation begins.',
    images: ['/banner.png'],
  },
  icons: {
    icon: [
      { url: '/favicon.ico' },
      { url: '/icon.png', type: 'image/png' },
    ],
    apple: [{ url: '/apple-icon.png' }],
  },
}

export const viewport: Viewport = {
  colorScheme: 'light',
  themeColor: '#FAF8F5',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="apple-touch-icon" href="/apple-icon.png" />
      </head>
      <body className="antialiased" suppressHydrationWarning>
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}

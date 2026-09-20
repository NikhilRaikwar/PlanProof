import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'PlanProof — Ideas to Verified Outcomes | Confidence Before Code',
  description:
    'Evidence-bound verification for AI-native engineering plans. PlanProof pressure-tests assumptions against your real codebase, AST structures, and dependency graphs before coding agents execute.',
  keywords: [
    'PlanProof',
    'plan verification',
    'AI code verification',
    'software architecture',
    'AST analysis',
    'dependency graphs',
    'codebase evidence',
    'automated gating',
    'developer tools',
    'coding agents',
    'pre-flight verification',
    'engineering plans',
  ],
  authors: [{ name: 'PlanProof' }],
  creator: 'PlanProof',
  publisher: 'PlanProof',
  applicationName: 'PlanProof',
  metadataBase: new URL('https://planproof.dev'),
  openGraph: {
    title: 'PlanProof — Ideas to Verified Outcomes | Confidence Before Code',
    description:
      'Evidence-bound verification for AI-native engineering plans. Test critical assumptions against real codebase evidence before building.',
    url: 'https://planproof.dev',
    siteName: 'PlanProof',
    images: [
      {
        url: '/logo.png',
        width: 1024,
        height: 1024,
        alt: 'PlanProof — Ideas to Verified Outcomes',
      },
    ],
    locale: 'en_US',
    type: 'website',
  },
  twitter: {
    card: 'summary',
    title: 'PlanProof — Ideas to Verified Outcomes',
    description:
      'Evidence-bound verification for AI-native engineering plans. Turn ambitious plans into verified steps.',
    images: ['/logo.png'],
    creator: '@planproof',
  },
  icons: {
    icon: [
      {
        url: '/logo.png',
        type: 'image/png',
      },
    ],
    shortcut: '/logo.png',
    apple: '/logo.png',
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
        <link rel="icon" href="/logo.png" type="image/png" />
        <link rel="apple-touch-icon" href="/logo.png" />
      </head>
      <body className="antialiased" suppressHydrationWarning>
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}

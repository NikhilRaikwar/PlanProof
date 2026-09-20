'use client'

import React, { useState } from 'react'
import { Copy, Check } from 'lucide-react'

export interface CodeBlockProps {
  code: string
  filePath?: string
  lines?: string
  language?: string
}

export function CodeBlock({ code, filePath, lines, language = 'python' }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{ borderRadius: 8, overflow: 'hidden', border: '1px solid #1E293B', background: '#0F172A' }}>
      {(filePath || lines) && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 14px',
          background: '#1E293B',
          borderBottom: '1px solid #334155',
          fontSize: 11.5,
          fontFamily: 'var(--font-mono)',
          color: '#94A3B8'
        }}>
          <span style={{ color: '#F8FAFC', fontWeight: 650 }}>{filePath}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {lines && <span>Lines {lines}</span>}
            <button
              onClick={handleCopy}
              style={{
                background: 'none',
                border: 'none',
                color: copied ? '#34D399' : '#94A3B8',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 11
              }}
              title="Copy code"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
        </div>
      )}

      <pre style={{
        margin: 0,
        padding: '14px 16px',
        color: '#F8FAFC',
        fontFamily: 'var(--font-mono)',
        fontSize: 11.5,
        lineHeight: 1.55,
        overflowX: 'auto'
      }}>
        <code>{code}</code>
      </pre>
    </div>
  )
}

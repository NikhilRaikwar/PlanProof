'use client'

import { useState } from 'react'
import Image from 'next/image'
import { motion, AnimatePresence, type Variants } from 'framer-motion'
import { 
  ArrowRight, 
  Check, 
  FileText, 
  GitBranch, 
  Rocket,
  Search, 
  ShieldCheck, 
  Sparkles, 
  Wrench,
  Code2,
  Layers
} from 'lucide-react'
import Link from 'next/link'

// Animation variants
const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: { 
    opacity: 1, 
    y: 0, 
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] as const } 
  }
}

const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.12
    }
  }
}

// Custom inline SVGs for Github & Play
function GithubIcon({ className = "w-3.5 h-3.5", size = 15 }: { className?: string; size?: number }) {
  return (
    <svg 
      width={size} 
      height={size} 
      className={className} 
      viewBox="0 0 24 24" 
      fill="currentColor"
      style={{ width: `${size}px`, height: `${size}px`, minWidth: `${size}px`, minHeight: `${size}px`, flexShrink: 0 }}
    >
      <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  )
}

function PlayIcon({ className = "w-3 h-3", size = 11 }: { className?: string; size?: number }) {
  return (
    <svg 
      width={size} 
      height={size} 
      className={className} 
      viewBox="0 0 24 24" 
      fill="currentColor"
      style={{ width: `${size}px`, height: `${size}px`, minWidth: `${size}px`, minHeight: `${size}px`, flexShrink: 0 }}
    >
      <path d="M8 5v14l11-7z" />
    </svg>
  )
}

// -------------------------------------------------------------
// SCENE 1: HERO SECTION
// -------------------------------------------------------------
function HeroSection() {
  return (
    <section className="scene-hero scene-hero-centered" id="hero">
      {/* Subtle warm ambient glows on empty sides */}
      <div className="hero-ambient-glow hero-glow-left" aria-hidden="true" />
      <div className="hero-ambient-glow hero-glow-right" aria-hidden="true" />

      <div className="scene-container relative">
        {/* Centered Hero Copy & Actions */}
        <motion.div 
          className="hero-copy-centered"
          initial="hidden"
          animate="visible"
          variants={staggerContainer}
        >
          {/* Eyebrow Pill */}
          <motion.div variants={fadeInUp} className="hero-kicker-pill">
            <Rocket className="w-3.5 h-3.5 text-orange-600 rotate-45" />
            <span>FROM PLAN TO PROOF</span>
          </motion.div>

          {/* Catch Headline */}
          <motion.h1 variants={fadeInUp} className="hero-title-centered">
            Verify the plan before<br />
            <span className="text-gradient-orange">agents build it.</span>
          </motion.h1>

          {/* Lede / Subtitle */}
          <motion.p variants={fadeInUp} className="hero-lede-centered">
            PlanProof checks engineering plans against your codebase, finds risky assumptions, and returns evidence-backed decisions before implementation begins.
          </motion.p>

          {/* Action CTAs */}
          <motion.div variants={fadeInUp} className="hero-actions-centered">
            <Link href="/workspace/new-verification" className="btn-primary-coral">
              <span>Start for free</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <a href="#how-it-works" className="btn-secondary-light">
              <div className="play-icon-circle-light">
                <PlayIcon className="w-2.5 h-2.5 fill-current ml-0.5" />
              </div>
              <span>Watch demo</span>
            </a>
          </motion.div>

          {/* Trust Points */}
          <motion.div variants={fadeInUp} className="hero-trust-note">
            <div className="trust-item">
              <Check className="trust-check-icon" />
              <span>Free for public repositories</span>
            </div>
            <div className="trust-item">
              <Check className="trust-check-icon" />
              <span>Zero build time setup</span>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}

// -------------------------------------------------------------
// SCENE 2: CONFIDENCE BEFORE CODE (3 Light Feature Cards)
// -------------------------------------------------------------
const confidenceSteps = [
  {
    number: '01',
    stepTag: 'ASSUMPTION PARSING',
    icon: FileText,
    title: 'Extract obligations',
    text: 'Turn plan assumptions into clear proof obligations that can be tested.',
    chips: ['Assumptions', 'Proof Claims', 'Constraints'],
    footer: 'Step 1 • Assumption Parsing'
  },
  {
    number: '02',
    stepTag: 'CODE GROUNDING',
    icon: Search,
    title: 'Gather evidence',
    text: 'Trace decisions back to repository facts, AST structures, and dependency graphs.',
    chips: ['AST Facts', 'Call Graphs', 'Symbol Index'],
    footer: 'Step 2 • Code Grounding'
  },
  {
    number: '03',
    stepTag: 'AUTOMATED GATE',
    icon: ShieldCheck,
    title: 'Gate the plan',
    text: 'Verify, disprove, or surface what needs a human before a single line is written.',
    chips: ['Verified Safe', 'Disproved', 'Human Escalation'],
    footer: 'Step 3 • Automated Gate'
  }
]

function ConfidenceSection() {
  return (
    <section className="scene-section scene-confidence" id="proof">
      <div className="scene-container">
        {/* Section Header */}
        <motion.div 
          className="section-header centered"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.35 }}
          variants={fadeInUp}
        >
          <div className="scene-kicker">
            <span className="kicker-line" />
            <span className="kicker-badge">FROM PLAN TO PROOF</span>
            <span className="kicker-line" />
          </div>
          <h2 className="scene-title">
            Confidence before code.
          </h2>
          <p className="scene-subtitle">
            Turn ambitious plans into verifiable steps. PlanProof helps you pressure-test ideas 
            against your actual codebase, so you avoid surprises and ship with confidence.
          </p>
        </motion.div>

        {/* 3 Light Cards Grid */}
        <div className="confidence-cards-grid">
          {confidenceSteps.map((card, idx) => {
            const Icon = card.icon
            return (
              <motion.div
                key={card.number}
                className="confidence-card"
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.2 }}
                transition={{ duration: 0.5, delay: idx * 0.12 }}
              >
                <div className="confidence-card-header">
                  <div className="confidence-step-meta">
                    <span className="confidence-num">{card.number}</span>
                    <span className="confidence-steptag">{card.stepTag}</span>
                  </div>
                  <div className="confidence-icon-box">
                    <Icon className="confidence-icon" />
                  </div>
                </div>

                <h3 className="confidence-card-title">{card.title}</h3>
                <p className="confidence-card-text">{card.text}</p>

                <div className="confidence-chips-wrap">
                  {card.chips.map(chip => (
                    <span key={chip} className="confidence-chip">
                      {chip}
                    </span>
                  ))}
                </div>

                <div className="confidence-card-foot">
                  <span className="confidence-foot-dot" />
                  <span>{card.footer}</span>
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

// -------------------------------------------------------------
// SCENE 3: A SIMPLE VERIFICATION FLOW (5 Step Nodes)
// -------------------------------------------------------------
const workflowSteps = [
  {
    id: 'connect',
    num: '01',
    label: 'Connect',
    sub: 'REPOSITORY',
    icon: GithubIcon,
    desc: 'Turn your GitHub repository (read-only).'
  },
  {
    id: 'plan',
    num: '02',
    label: 'Plan',
    sub: 'UPLOAD REQUEST',
    icon: FileText,
    desc: 'Describe what you want to build or upload a plan.'
  },
  {
    id: 'trace',
    num: '03',
    label: 'Trace',
    sub: 'CODEBASE PLANS',
    icon: GitBranch,
    desc: 'PlanProof generates a plan with clear assumptions.'
  },
  {
    id: 'check',
    num: '04',
    label: 'Check',
    sub: 'EVIDENCE',
    icon: Search,
    desc: 'We trace each claim to your real codebase facts.'
  },
  {
    id: 'decide',
    num: '05',
    label: 'Decide',
    sub: 'GREEN OR RED LIGHT',
    icon: ShieldCheck,
    desc: "See what's verified, disproved, or needs a human."
  }
]

function WorkflowSection() {
  const [hoveredNode, setHoveredNode] = useState<number | null>(null)

  return (
    <section className="scene-section scene-workflow" id="how-it-works">
      <div className="scene-container">
        {/* Section Header */}
        <motion.div 
          className="section-header centered"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.35 }}
          variants={fadeInUp}
        >
          <div className="scene-kicker">
            <span className="kicker-line" />
            <span className="kicker-badge">HOW IT WORKS</span>
            <span className="kicker-line" />
          </div>
          <h2 className="scene-title">
            A simple <span className="text-gradient-orange">verification</span> flow.
          </h2>
          <p className="scene-subtitle">
            From code to confident decisions, in five steps.
          </p>
        </motion.div>

        {/* 5-Step Pipeline */}
        <div className="workflow-centered-stage">
          <div className="diagram-stage">
            <div className="flow-interactive-track">
              {workflowSteps.map((node, i) => {
                const Icon = node.icon
                const isHovered = hoveredNode === i
                const isLast = i === workflowSteps.length - 1

                return (
                  <div key={node.id} className="flow-step-item-wrap">
                    {/* Node Item */}
                    <div 
                      className={`node-card-item ${isHovered ? 'node-highlight' : ''}`}
                      onMouseEnter={() => setHoveredNode(i)}
                      onMouseLeave={() => setHoveredNode(null)}
                    >
                      <div className="node-icon-box">
                        <Icon className="node-icon" />
                      </div>

                      <div className="node-meta-wrap">
                        <div className="node-title-row">
                          <span className="node-mobile-num">{node.num}</span>
                          <strong className="node-label">{node.label}</strong>
                        </div>
                        <span className="node-sublabel">{node.sub}</span>
                        <p className="node-mobile-desc">{node.desc}</p>
                      </div>
                    </div>

                    {/* Connecting Orange Wave Segment */}
                    {!isLast && (
                      <div className="flow-connector-segment">
                        <svg className="segment-svg" viewBox="0 0 100 36" fill="none" preserveAspectRatio="none">
                          <defs>
                            <linearGradient id={`orangeGrad-${i}`} x1="0%" y1="50%" x2="100%" y2="50%">
                              <stop offset="0%" stopColor="#FF4D2E" stopOpacity="0.9" />
                              <stop offset="100%" stopColor="#F97316" stopOpacity="0.9" />
                            </linearGradient>
                          </defs>

                          <path
                            d={i % 2 === 0 ? "M 0 18 Q 50 6 100 18" : "M 0 18 Q 50 30 100 18"}
                            stroke="#FDBA74"
                            strokeWidth="2"
                            strokeDasharray="4 4"
                          />

                          <motion.path
                            d={i % 2 === 0 ? "M 0 18 Q 50 6 100 18" : "M 0 18 Q 50 30 100 18"}
                            stroke={`url(#orangeGrad-${i})`}
                            strokeWidth="2.5"
                            initial={{ pathLength: 0 }}
                            whileInView={{ pathLength: 1 }}
                            viewport={{ once: true, amount: 0.35 }}
                            transition={{ duration: 0.9, delay: 0.2 + i * 0.12, ease: "easeInOut" }}
                          />

                          <circle r="3.5" fill="#EA580C">
                            <animateMotion
                              path={i % 2 === 0 ? "M 0 18 Q 50 6 100 18" : "M 0 18 Q 50 30 100 18"}
                              dur="1.8s"
                              begin={`${i * 0.3}s`}
                              repeatCount="indefinite"
                            />
                          </circle>
                        </svg>

                        {/* Mobile Stepper Connector Line */}
                        <div className="flow-mobile-connector">
                          <span className="flow-mobile-line" />
                          <span className="flow-mobile-dot" />
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Handwritten Tagline below stepper */}
            <motion.div 
              className="script-tagline"
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.6, delay: 0.6 }}
            >
              <span className="script-text">From idea to a plan you can trust.</span>
              <svg className="script-underline" viewBox="0 0 240 16" fill="none">
                <motion.path
                  d="M 5 10 Q 120 2 235 8"
                  stroke="#EA580C"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  initial={{ pathLength: 0 }}
                  whileInView={{ pathLength: 1 }}
                  viewport={{ once: true, amount: 0.4 }}
                  transition={{ duration: 1, delay: 0.8 }}
                />
              </svg>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  )
}

// -------------------------------------------------------------
// SCENE 4: WHY PLANPROOF (Connected System Ecosystem)
// -------------------------------------------------------------
const connectedQuadrants = [
  {
    id: 'repos',
    position: 'top-left',
    icon: Code2,
    title: 'Repositories',
    desc: 'Your codebase, in context.',
    tags: ['Code', 'Branches', 'Commits']
  },
  {
    id: 'evidence',
    position: 'top-right',
    icon: Search,
    title: 'Evidence explorer',
    desc: 'Trace every decision to source.',
    tags: ['Search', 'Correlate', 'Verify']
  },
  {
    id: 'traces',
    position: 'bottom-left',
    icon: Wrench,
    title: 'Tool traces',
    desc: 'See what tools found, step by step.',
    tags: ['Tools', 'Steps', 'Artifacts']
  },
  {
    id: 'evals',
    position: 'bottom-right',
    icon: ShieldCheck,
    title: 'Evaluations',
    desc: 'Objective checks, not guesswork.',
    tags: ['Tests', 'Checks', 'Confidence']
  }
]

function ConnectedSystemSection() {
  return (
    <section className="scene-section scene-connected" id="why">
      <div className="scene-container">
        {/* Section Header */}
        <motion.div 
          className="section-header centered"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.35 }}
          variants={fadeInUp}
        >
          <div className="scene-kicker">
            <span className="kicker-line" />
            <span className="kicker-badge">WHY PLANPROOF</span>
            <span className="kicker-line" />
          </div>
          <h2 className="scene-title">
            Everything connected for<br />
            <span className="text-gradient-orange">confident</span> plan verification.
          </h2>
          <p className="scene-subtitle">
            PlanProof connects your code, tools, and evidence so every decision is grounded in reality.
          </p>
        </motion.div>

        {/* Connected System Diagram */}
        <div className="connected-stage-wrap">
          {/* Radial SVG Beziers connecting Center <-> 4 Cards */}
          <svg className="connected-svg-desktop" viewBox="0 0 980 480" fill="none">
            <defs>
              <linearGradient id="connOrangeTL" x1="50%" y1="50%" x2="25%" y2="20%">
                <stop offset="0%" stopColor="#F97316" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#EA580C" stopOpacity="0.5" />
              </linearGradient>
              <linearGradient id="connOrangeTR" x1="50%" y1="50%" x2="75%" y2="20%">
                <stop offset="0%" stopColor="#F97316" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#EA580C" stopOpacity="0.5" />
              </linearGradient>
              <linearGradient id="connOrangeBL" x1="50%" y1="50%" x2="25%" y2="80%">
                <stop offset="0%" stopColor="#F97316" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#EA580C" stopOpacity="0.5" />
              </linearGradient>
              <linearGradient id="connOrangeBR" x1="50%" y1="50%" x2="75%" y2="80%">
                <stop offset="0%" stopColor="#F97316" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#EA580C" stopOpacity="0.5" />
              </linearGradient>
            </defs>

            {/* Top-Left Path (Center Circle Boundary -> Repositories Card) */}
            <motion.path
              d="M 420.7 170.7 C 375 130, 345 85, 310 85"
              stroke="url(#connOrangeTL)"
              strokeWidth="2.2"
              initial={{ pathLength: 0, opacity: 0 }}
              whileInView={{ pathLength: 1, opacity: 1 }}
              viewport={{ once: true, amount: 0.35 }}
              transition={{ duration: 1.1, ease: "easeInOut", delay: 0.2 }}
            />
            {/* Top-Left Anchor Nodes */}
            <circle cx="420.7" cy="170.7" r="3" fill="#EA580C" />
            <circle cx="310" cy="85" r="3" fill="#EA580C" />

            {/* Top-Right Path (Center Circle Boundary -> Evidence Explorer Card) */}
            <motion.path
              d="M 559.3 170.7 C 605 130, 635 85, 670 85"
              stroke="url(#connOrangeTR)"
              strokeWidth="2.2"
              initial={{ pathLength: 0, opacity: 0 }}
              whileInView={{ pathLength: 1, opacity: 1 }}
              viewport={{ once: true, amount: 0.35 }}
              transition={{ duration: 1.1, ease: "easeInOut", delay: 0.2 }}
            />
            {/* Top-Right Anchor Nodes */}
            <circle cx="559.3" cy="170.7" r="3" fill="#EA580C" />
            <circle cx="670" cy="85" r="3" fill="#EA580C" />

            {/* Bottom-Left Path (Center Circle Boundary -> Tool Traces Card) */}
            <motion.path
              d="M 420.7 309.3 C 375 350, 345 395, 310 395"
              stroke="url(#connOrangeBL)"
              strokeWidth="2.2"
              initial={{ pathLength: 0, opacity: 0 }}
              whileInView={{ pathLength: 1, opacity: 1 }}
              viewport={{ once: true, amount: 0.35 }}
              transition={{ duration: 1.1, ease: "easeInOut", delay: 0.2 }}
            />
            {/* Bottom-Left Anchor Nodes */}
            <circle cx="420.7" cy="309.3" r="3" fill="#EA580C" />
            <circle cx="310" cy="395" r="3" fill="#EA580C" />

            {/* Bottom-Right Path (Center Circle Boundary -> Evaluations Card) */}
            <motion.path
              d="M 559.3 309.3 C 605 350, 635 395, 670 395"
              stroke="url(#connOrangeBR)"
              strokeWidth="2.2"
              initial={{ pathLength: 0, opacity: 0 }}
              whileInView={{ pathLength: 1, opacity: 1 }}
              viewport={{ once: true, amount: 0.35 }}
              transition={{ duration: 1.1, ease: "easeInOut", delay: 0.2 }}
            />
            {/* Bottom-Right Anchor Nodes */}
            <circle cx="559.3" cy="309.3" r="3" fill="#EA580C" />
            <circle cx="670" cy="395" r="3" fill="#EA580C" />
          </svg>

          {/* Central PlanProof Clean Circular Hub */}
          <div className="connected-center-anchor">
            <motion.div 
              className="connected-center-node"
              whileHover={{ scale: 1.04 }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
            >
              <div className="core-cube-box">
                <Image 
                  src="/icon-cube.png" 
                  alt="PlanProof Core Mark" 
                  width={38} 
                  height={38} 
                  className="core-logo-img" 
                />
              </div>

              <div className="core-text-wrap">
                <span className="core-brand-text">PlanProof</span>
                <span className="core-sub-caption">IDEAS TO VERIFIED OUTCOMES</span>
              </div>
            </motion.div>
          </div>

          {/* 4 Corner Cards */}
          <div className="connected-cards-container">
            {connectedQuadrants.map((card, idx) => {
              const Icon = card.icon
              return (
                <motion.article 
                  key={card.id}
                  className={`connected-system-card card-${card.position}`}
                  initial={{ opacity: 0, y: 16 }}
                  whileInView={{ 
                    opacity: 1, 
                    y: 0,
                    transition: { duration: 0.5, delay: 0.15 + idx * 0.08, ease: "easeOut" }
                  }}
                  viewport={{ once: true, amount: 0.3 }}
                >
                  <div className="system-card-top">
                    <div className="system-icon-box">
                      <Icon className="system-icon" />
                    </div>
                    <div className="system-card-heading">
                      <h3 className="system-card-title">{card.title}</h3>
                      <p className="system-card-desc">{card.desc}</p>
                    </div>
                  </div>

                  <div className="system-tag-list">
                    {card.tags.map(tag => (
                      <span key={tag} className="system-pill-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </motion.article>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}

// -------------------------------------------------------------
// SCENE 5: FINAL CTA & LIGHT FOOTER
// -------------------------------------------------------------
function CtaSection() {
  return (
    <section className="scene-cta" id="cta">
      <div className="scene-container">
        {/* Wide Warm Cream CTA Card */}
        <motion.div 
          className="cta-banner-card"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.4 }}
          variants={fadeInUp}
        >
          {/* Decorative side sparkle rays */}
          <svg className="cta-rays-left hidden md:block" width="40" height="40" viewBox="0 0 40 40" fill="none">
            <path d="M 5 20 L 15 20 M 8 10 L 16 16 M 8 30 L 16 24" stroke="#FDBA74" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <svg className="cta-rays-right hidden md:block" width="40" height="40" viewBox="0 0 40 40" fill="none">
            <path d="M 35 20 L 25 20 M 32 10 L 24 16 M 32 30 L 24 24" stroke="#FDBA74" strokeWidth="2" strokeLinecap="round" />
          </svg>

          <h2 className="cta-headline">
            Make the next change easier to trust.
          </h2>
          <p className="cta-copy">
            Verify your plans against real code. Catch risky assumptions early.<br className="hidden sm:inline" />
            Ship with confidence.
          </p>
          <div className="cta-actions">
            <Link href="/workspace/new-verification" className="btn-primary-coral">
              <span>Start a verification</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link href="/workspace/new-verification" className="btn-secondary-light">
              <GithubIcon className="w-3.5 h-3.5" />
              <span>Connect GitHub</span>
            </Link>
          </div>
        </motion.div>
      </div>

      {/* Minimal Light Footer */}
      <footer className="site-footer">
        <div className="scene-container">
          <div className="footer-minimal-wrap">
            {/* Brand Left */}
            <div className="footer-brand-side">
              <div className="footer-brand-header">
                <div className="footer-logo-box">
                  <Image src="/logo.png" alt="PlanProof" width={26} height={26} className="object-contain" />
                </div>
                <span className="footer-brand-title">PlanProof</span>
                <span className="footer-beta-tag">BETA</span>
              </div>
              <p className="footer-brand-desc">
                Deterministic verification for engineering plans before code is written.
              </p>
            </div>

            {/* GitHub Repo Showcase Right */}
            <div className="footer-repo-side">
              <a 
                href="https://github.com/nikhilraikwar/planproof" 
                target="_blank" 
                rel="noopener noreferrer" 
                className="footer-github-card"
              >
                <div className="github-card-icon">
                  <GithubIcon className="w-3.5 h-3.5" />
                </div>
                <div className="github-card-info">
                  <span className="github-card-repo">nikhilraikwar / planproof</span>
                  <span className="github-card-sub">Open Source Repository</span>
                </div>
                <div className="github-card-action">
                  <span className="github-star-badge">★ Star on GitHub</span>
                </div>
              </a>
            </div>
          </div>

          {/* Bottom Sub-Footer Bar */}
          <div className="footer-bottom-bar">
            <div className="footer-copyright">
              © 2026 PlanProof Inc. All rights reserved.
            </div>

            <div className="footer-status-pill">
              <span className="footer-status-dot" />
              <span>Verification Engine Operational</span>
            </div>
          </div>
        </div>
      </footer>
    </section>
  )
}

// -------------------------------------------------------------
// MAIN LANDING PAGE COMPONENT
// -------------------------------------------------------------
export default function LandingPage() {
  return (
    <div className="planproof-landing-root">
      {/* Sticky / Fixed Glassmorphic Navigation Bar */}
      <header className="site-nav">
        <div className="nav-container">
          <Link href="/" className="nav-brand">
            <span className="nav-logo-box">
              <Image src="/logo.png" alt="PlanProof Logo" width={26} height={26} className="nav-logo-img" priority />
            </span>
            <span className="nav-brand-title">PlanProof</span>
          </Link>

          {/* Streamlined Menu Links */}
          <nav className="nav-menu">
            <a href="#how-it-works" className="nav-link">How it works</a>
            <a href="#why" className="nav-link">Why PlanProof</a>
          </nav>

          <div className="nav-right">
            <Link 
              href="/workspace/new-verification" 
              className="nav-github-btn"
            >
              <GithubIcon className="w-3.5 h-3.5" />
              <span>Connect GitHub</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Viewport Content */}
      <main className="landing-scenes-wrapper">
        <HeroSection />
        <ConfidenceSection />
        <WorkflowSection />
        <ConnectedSystemSection />
        <CtaSection />
      </main>
    </div>
  )
}

import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

const patterns = [
  /mongodb\+srv:\/\/[^\s"']+/i,
  /-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----/,
  /(?:OPENROUTER_API_KEY|AIMLAPI_API_KEY|MONGODB_URI|REDIS_URL)\s*=\s*(?!["']?(?:$|\$\{|<|YOUR_|CHANGEME))["']?[^\s"']{12,}/,
]
const files = execFileSync('git', ['ls-files', '-z'], { encoding: 'utf8' })
  .split('\0')
  .filter(Boolean)
  // Product requirement/plan documents can contain deliberately fake connection-string syntax.
  .filter(file => !['.env.example', 'PLANPROOF_PRD.md', 'PLANPROOF_ENGINEERING_BUILD_PLAN.md'].includes(file))

const findings = []
for (const file of files) {
  const text = readFileSync(file, 'utf8')
  for (const pattern of patterns) {
    if (pattern.test(text)) findings.push(file)
  }
}

if (findings.length) {
  throw new Error(`Potential credential material detected in: ${[...new Set(findings)].join(', ')}`)
}

console.log('Secret scan passed: no tracked credential patterns detected.')

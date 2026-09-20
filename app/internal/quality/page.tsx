import { ShieldCheck } from 'lucide-react'

export default function InternalQualityPage() {
  return <div className="card-panel-white" style={{ textAlign: 'center', padding: 64 }}>
    <ShieldCheck size={28} style={{ color: '#EA580C' }} />
    <h1 className="page-main-title">Internal quality</h1>
    <p className="page-main-desc">No evaluation runs recorded yet.</p>
  </div>
}

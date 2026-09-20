import { redirect } from 'next/navigation'

export default function WorkspaceEvaluationsRedirect() {
  redirect('/internal/quality')
}

import asyncio

from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.runs import VerificationRun, VerificationRunStatus
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.workflow.engine import VerificationWorkflow


async def run_smoke():
    settings = Settings()
    mongo = MongoManager(settings)
    await mongo.connect()
    db = mongo.database()
    
    runs_repo = RunRepository(mongo)
    verif_repo = VerificationRepository(mongo)
    
    project_id = "271c3d3e-6fd5-44c0-a8ee-89e52ca589fe"
    snapshot_id = "6d090775-57a6-4a8a-8016-eed3c916e94c"
    plan_version_id = "f96a44c7-944a-4aec-871a-ebf489dc04a8"
    
    run = VerificationRun(
        project_id=project_id,
        snapshot_id=snapshot_id,
        plan_version_id=plan_version_id,
        status=VerificationRunStatus.QUEUED,
    )
    await runs_repo.create_run(run)
    print(f"SMOKE_RUN_ID={run.id}", flush=True)
    
    workflow = VerificationWorkflow(runs_repo, verif_repo, settings)
    await workflow.run(run.id)
    print(f"SMOKE_RUN_COMPLETED={run.id}", flush=True)
    
    # Detailed Telemetry
    run_doc = await db.verification_runs.find_one({"id": run.id})
    obs = await db.proof_obligations.find({"run_id": run.id}).to_list(50)
    evs = await db.evidence.find({"run_id": run.id}).to_list(50)
    tools = await db.tool_runs.find({"run_id": run.id}).to_list(50)
    revised = await db.revised_plans.find_one({"run_id": run.id})
    
    print("=" * 70, flush=True)
    print(f"SMOKE REPORT - RUN ID: {run.id}", flush=True)
    print(f"RUN STATUS: {run_doc.get('status')}", flush=True)
    print(f"DETERMINISTIC GATE VERDICT: {run_doc.get('gate_verdict')}", flush=True)
    print(f"TOOL CALL COUNT: {run_doc.get('tool_call_count')}", flush=True)
    print(f"EVIDENCE COUNT: {len(evs)}", flush=True)
    print(f"TOOL EXECUTIONS COUNT: {len(tools)}", flush=True)
    print("-" * 70, flush=True)
    print("PROOF OBLIGATIONS:", flush=True)
    for ob in obs:
        print(f"  [{ob.get('status')}] (role={ob.get('semantic_role')}) statement: {ob.get('statement')}", flush=True)
        if ob.get('evidence_ids'):
            print(f"      evidence_ids: {ob.get('evidence_ids')}", flush=True)
        if ob.get('counter_evidence_ids'):
            print(f"      counter_evidence_ids: {ob.get('counter_evidence_ids')}", flush=True)
    print("-" * 70, flush=True)
    print("TOOL RUNS / EXECUTIONS:", flush=True)
    for t in tools:
        print(f"  Tool: {t.get('tool_name')} args={t.get('tool_arguments')}", flush=True)
    print("-" * 70, flush=True)
    print("EVIDENCE ITEMS:", flush=True)
    for ev in evs:
        print(f"  Ev: type={ev.get('evidence_type')} path={ev.get('path')} rel={ev.get('relationship')} summary={ev.get('summary')}", flush=True)
    print("-" * 70, flush=True)
    if revised:
        print(f"REVISED PLAN TITLE: {revised.get('title')}", flush=True)
        print(f"REVISED PLAN SUMMARY: {revised.get('summary')}", flush=True)
        for st in revised.get("steps", []):
            print(f"  Step {st.get('step_number')}: [{st.get('action')}] {st.get('target_path')} - {st.get('description')}", flush=True)
    print("=" * 70, flush=True)
    
    await mongo.close()

if __name__ == "__main__":
    asyncio.run(run_smoke())

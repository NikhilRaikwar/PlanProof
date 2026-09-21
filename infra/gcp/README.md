# GCP infrastructure helpers

`preflight.ps1` performs read-only prerequisite checks for the documented `planproof-ai` / `asia-south1` target. It never prints secret values and never creates or destroys resources.

Run it only after installing/authenticating the Google Cloud CLI:

```powershell
./infra/gcp/preflight.ps1
```

See `docs/DEPLOYMENT_GCP.md` for the deliberate deployment sequence and security constraints.

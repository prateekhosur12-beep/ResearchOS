# 07 — Windows (PowerShell) Commands

Everything below was verified on Linux; the commands are the PowerShell equivalents of
the exact commands used for the recorded results in doc 08. Run them from the project
root unless stated otherwise.

## 0. Prerequisites

```powershell
winget install --id Python.Python.3.12 -e      # or 3.11+
winget install --id OpenJS.NodeJS.LTS -e
# Ollama (optional but recommended for the LLM prose paths)
winget install --id Ollama.Ollama -e
ollama --version
```

Verify:

```powershell
python --version       # 3.11+
node --version         # 18+
npm --version
```

## 1. Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# If PowerShell blocks activation:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env      # then edit SCHOLARLY_CONTACT_EMAIL
```

Create the database and run the API:

```powershell
python -c "import asyncio; from app.db.base import init_db; asyncio.run(init_db()); print('db ready')"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check (new terminal):

```powershell
Invoke-RestMethod http://localhost:8000/api/health | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/api/system/status | ConvertTo-Json -Depth 5
```

Expect `status: ok`; `llm.available` reflects whether `ollama serve` is actually running.

## 2. Ollama (optional, needed for LLM-written prose)

```powershell
ollama serve                  # leave running in its own window
ollama pull qwen2.5:3b        # ~2 GB chat model used by the agents
ollama pull nomic-embed-text  # ~275 MB embeddings (separate model)
ollama list                   # confirm both names appear
```

Then re-check:

```powershell
Invoke-RestMethod http://localhost:8000/api/system/status |
  Select-Object -ExpandProperty llm | ConvertTo-Json
```

With the daemon down the app still works; it reports *"LLM unavailable"* and uses the
deterministic paths. Nothing is faked.

## 3. Frontend

**Option A — production build served by FastAPI (recommended; one origin, no CORS):**

```powershell
cd ..\frontend
npm install
npm run build            # tsc -b && vite build  ->  ..\backend\static\ui
cd ..\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000/
```

**Option B — Vite dev server with hot reload (proxy to :8000):**

```powershell
# terminal 1
cd backend; .\.venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --port 8000

# terminal 2
cd frontend; npm run dev
# open http://localhost:5173/
```

`vite.config.ts` proxies `/api` to `http://localhost:8000`, so no browser-side absolute
URLs are needed.

## 4. Running a research project from PowerShell (API only)

```powershell
$base = "http://localhost:8000/api"

# create a project
$project = Invoke-RestMethod -Method Post -Uri "$base/projects" -ContentType "application/json" `
  -Body (@{ name = "Road Anomaly Detection"; topic = "road anomaly detection using YOLO"; domain = "computer_science" } | ConvertTo-Json)
$pid = $project.id

# start a run
$run = Invoke-RestMethod -Method Post -Uri "$base/projects/$pid/runs" -ContentType "application/json" `
  -Body (@{ result_limit = 10; min_papers = 5; generate_draft = $true; run_radar = $true; run_collaboration = $true } | ConvertTo-Json)

# poll until it pauses at the approval gate (typically 5-15 s)
do {
  Start-Sleep -Seconds 3
  $detail = Invoke-RestMethod -Uri "$base/runs/$($run.id)"
  Write-Host $detail.status $detail.stage
} while ($detail.status -in @("pending", "running"))

# inspect what was retrieved
Invoke-RestMethod -Uri "$base/projects/$pid/papers" | Select-Object -ExpandProperty papers |
  Select-Object year, title, @{n='sources';e={$_.sources -join ','}} | Format-Table

# export is blocked until you approve
try {
  Invoke-RestMethod -Method Post -Uri "$base/projects/$pid/exports" -ContentType "application/json" -Body '{"kind":"manuscript_md"}'
} catch { Write-Host "HTTP $($_.Exception.Response.StatusCode.value__) — gate working" }

$approval = (Invoke-RestMethod -Uri "$base/projects/$pid/approvals").approvals[0]
Invoke-RestMethod -Method Post -Uri "$base/approvals/$($approval.id)/decide" -ContentType "application/json" `
  -Body '{"decision":"approved","actor":"student","note":"checked against sources"}'

# now the export succeeds and lands in backend\exports\<project_id>\
Invoke-RestMethod -Method Post -Uri "$base/projects/$pid/exports" -ContentType "application/json" -Body '{"kind":"manuscript_md"}'
```

> Note the decision value is `approved` / `rejected` (not `approve`); the API returns a
> 422 with that exact hint if you get it wrong.

## 5. Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1

python -m pytest -q                      # 79 offline tests
python -m pytest -q -m "not slow"        # skip the MCP-subprocess tests
python -m pytest -q -k lab05 -v          # one lab
$env:RUN_LIVE_TESTS=1; python -m pytest tests/test_live_services.py -v   # real APIs
Remove-Item Env:\RUN_LIVE_TESTS
```

Full end-to-end proof against the live APIs (writes to `smoke_e2e.db`, not your data):

```powershell
python smoke_e2e.py "federated learning for IoT security"
```

## 6. Common Windows issues

| Symptom | Cause | Fix |
|---|---|---|
| `Activate.ps1 cannot be loaded` | execution policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| `python` opens the Microsoft Store | App Execution Alias | use `py -3.12`, or disable the alias in Settings → Apps → App execution aliases |
| `greenlet` build error | missing wheel for an odd Python version | use Python 3.11–3.13, or `pip install --only-binary :all: greenlet` |
| `[WinError 10013]` on port 8000 | port blocked/reserved | `python -m uvicorn app.main:app --port 8010` |
| MCP subprocess fails to start | wrong working directory / venv not active | run from `backend\` with the venv active; the runner falls back to the in-process registry and says so in `transport_note` |
| `curl` gives odd output | `curl` is an alias for `Invoke-WebRequest` in PowerShell | use `Invoke-RestMethod`, or `curl.exe` |
| Ollama "model not installed" | pulled under a different tag | `ollama list`, then set `OLLAMA_MODEL` to the exact name |
| Firewall prompt for uvicorn | first bind to 0.0.0.0 | allow on private networks |

## 7. Path handling note

Use `Copy-Item`, `Remove-Item`, `Test-Path`, `New-Item -ItemType Directory` rather than
POSIX commands; the codebase itself is path-agnostic (`pathlib` everywhere), and export
filenames are sanitised server-side, so Windows path separators cannot be injected.

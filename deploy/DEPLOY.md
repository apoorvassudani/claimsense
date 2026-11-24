# Deploying ClaimSense to Azure

One **App Service** runs the API and the React app at a single address (`https://YOUR-APP.azurewebsites.net`),
backed by **Azure Database for PostgreSQL**. Your existing Azure OpenAI and Azure AI Search resources are reused.

```
Browser ──> App Service (gunicorn + FastAPI)
              ├── /          React app (frontend/dist)
              ├── /api/...   the API (same routes as locally; Swagger at /api/docs)
              ├──> Azure Database for PostgreSQL
              ├──> Azure OpenAI (gpt-4.1-mini, text-embedding-3-small)
              └──> Azure AI Search (policy-clauses)
```

Total time: about 75–90 minutes. Start the database first: it takes 10–15 minutes to create.

---

## Before you start (the night before, 10 minutes)

1. **Permission check.** In the Azure portal, open *Create a resource* for **Web App** and for **Azure Database for
   PostgreSQL flexible server**. If either says you are not allowed, record the blocker and use the local demo.
2. **Install the Azure CLI** (PowerShell): `winget install -e --id Microsoft.AzureCLI`, then open a new terminal and
   run `az login`.
3. **Install the new packages** (from `claimsense\backend`, venv active): `pip install -r requirements.txt`

Use **one resource group and one region** for everything (the same region as your Azure OpenAI resource).

---

## Step 1 · Create the database (5 min, then 10–15 min waiting)

Portal → *Create a resource* → **Azure Database for PostgreSQL flexible server** → Create.

| Setting | Value |
|---|---|
| Resource group | your existing one |
| Server name | `claimsense-db-yourname` (must be unique) |
| Region | same as your other resources |
| PostgreSQL version | 16 |
| Workload type | **Development** (Burstable, B1ms: the cheapest) |
| Authentication | PostgreSQL authentication only |
| Admin username | `claimsadmin` |
| Password | **letters and digits only** (no `@ : / # ?`, they break the connection string) |

**Networking** tab: *Public access* →
- tick **Allow public access from any Azure service within Azure to this server**
- click **+ Add current client IP address** (so your laptop can load the data)

Review + create. **Don't wait: go to Step 2.**

## Step 2 · Create the Web App (5 min)

Portal → *Create a resource* → **Web App** → Create.

| Setting | Value |
|---|---|
| Name | `claimsense-yourname` (becomes `claimsense-yourname.azurewebsites.net`) |
| Publish | **Code** |
| Runtime stack | **Python 3.12** |
| Operating system | Linux |
| Region | same as the database |
| Pricing plan | **Basic B1** (or Free F1 if cost is a concern: slower, sleeps when idle) |

Review + create.

## Step 3 · Set the startup command (2 min)

Web App → **Settings → Configuration** → *General settings* (or *Stack settings*) → **Startup Command**:

```
gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:8000 --timeout 120 --chdir backend app.serve:root
```

Save.

## Step 4 · Build the deployment package (3 min)

From the `claimsense` folder, venv active:

```powershell
python deploy/make_package.py
```

It builds the React app for production and creates `deploy\claimsense-app.zip`.

## Step 5 · Settings: your .env, moved to the cloud (5 min)

When the database shows **Deployment complete**, open it and copy the **Server name** from Overview
(e.g. `claimsense-db-yourname.postgres.database.azure.com`). Then:

```powershell
python deploy/env_to_appsettings.py "postgresql+psycopg://claimsadmin:YOURPASSWORD@SERVERNAME:5432/postgres?sslmode=require"
```

It reads `backend\.env`, swaps in the cloud database, adds a fresh `AUTH_SECRET` and the deployment settings, and
writes `deploy\appsettings.json`. It also prints the **sign-in password** for the cloud app.

Web App → **Settings → Environment variables** → *App settings* → **Advanced edit** → replace the contents with the
file's contents → OK → **Apply / Save** (the app restarts). Then **delete `deploy\appsettings.json`**: it contains
your keys.

## Step 6 · Load the data into the cloud database (5–15 min)

From `claimsense\backend`, venv active, point your laptop at the cloud database for this one command:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://claimsadmin:YOURPASSWORD@SERVERNAME:5432/postgres?sslmode=require"
python -m app.seed --live        # real Azure extraction + briefings (~10–15 min)
# short of time? use:  python -m app.seed      (instant; offline extraction, briefings from templates)
Remove-Item Env:DATABASE_URL     # back to your local database
```

The policy index in Azure AI Search is already built and shared, so there is no need to run `rag_index` again.

## Step 7 · Deploy the app (5–10 min)

```powershell
az webapp deploy --resource-group YOUR-RG --name claimsense-yourname --src-path deploy/claimsense-app.zip --type zip
```

App Service unpacks the zip and installs `requirements.txt` (a few minutes). Wait for it to finish.

*No Azure CLI?* In VS Code install the **Azure App Service** extension, sign in, unzip `claimsense-app.zip` into a
folder, right-click your web app → **Deploy to Web App…** → choose that folder.

## Step 8 · Smoke test (10 min)

| Check | Expected |
|---|---|
| `https://YOUR-APP.azurewebsites.net/health` | `{"status":"ok"}` |
| `https://YOUR-APP.azurewebsites.net/api/health` | `"model":"azure:gpt-4.1-mini"`, `"retrieval":"azure_ai_search_hybrid"` |
| `https://YOUR-APP.azurewebsites.net` | Sign-in page; sign in as `reviewer01` |
| Claims queue | 84 claims |
| Open a HIGH claim | Briefing, flags, policy clauses |
| New claim → upload → verify | Runs end to end with live Azure calls |
| Monitoring | Runs, error rate, p95 latency |
| Reload the page on any screen | Stays on that screen, still signed in |

First request after a restart can take 20–30 seconds while the app starts.

---

## Step 9 · Load test the live app (5 min)

From `claimsense\backend`, venv active:

```powershell
python -m app.load_test --url https://YOUR-APP.azurewebsites.net/api --users 20 --duration 60
```

Prints throughput, errors and p50/p95/p99 latency per request type and saves `docs\load-test-report.md`
(targets: p95 under 1 s, errors under 1%). Verification is excluded because every run calls the paid model.

## Step 10 · Turn on CD (5 min, needs the code on GitHub)

The pipeline in `.github/workflows/ci.yml` runs the tests and builds the frontend on every push, and deploys to
App Service on every push to `main` once configured:

1. Web App → **Settings → Configuration → General settings** → turn on **SCM Basic Auth Publishing Credentials** → Save.
2. Web App → **Overview → Download publish profile**.
3. GitHub repo → **Settings → Secrets and variables → Actions**:
   secret `AZURE_WEBAPP_PUBLISH_PROFILE` = the file's contents; variable `AZURE_WEBAPP_NAME` = your app name.
4. Push to `main` (or *Actions → ci-cd → Run workflow*). The run ends with a health check on the live site.

---

## If something goes wrong

Web App → **Monitoring → Log stream** shows what the app prints.

| Symptom | Likely cause | Fix |
|---|---|---|
| "Application Error" page | App didn't start | Log stream; check the startup command (Step 3) |
| `ModuleNotFoundError` in the log | Packages not installed | Check `SCM_DO_BUILD_DURING_DEPLOYMENT=true` is in App settings, then deploy again |
| Database connection timeout | Firewall | Database → Networking: "Allow public access from any Azure service" ticked; for Step 6, your IP added |
| `password authentication failed` | Wrong password or special characters | Reset the admin password (letters and digits only) and update `DATABASE_URL` |
| Sign-in always fails | Users created with another password | Sign-in password is your `.env` `DEMO_PASSWORD` (Step 5 prints it) |
| `/api/health` shows `mock` | Settings not applied | Check `LLM_PROVIDER=azure` and the `AZURE_OPENAI_*` settings, then restart |
| "Frontend not built" message | Zip made without the build | Rerun `python deploy/make_package.py`, deploy again |

If deployment is blocked or runs out of time, the local setup is the demo. Write down what blocked it.

## After the assessment: cost

App Service B1 and PostgreSQL B1ms are billed while they exist. **Stop** the database (Overview → Stop) and the
web app when you are not using them, and **delete** them when the project is finished.

## Later: Document Intelligence

Add `AZURE_DOCINTEL_ENDPOINT` and `AZURE_DOCINTEL_API_KEY` to the App settings and save. `OCR_PROVIDER=auto`
switches to it automatically; `/api/health` shows `"ocr": "azure-docintel:prebuilt-read"`. No redeploy needed.

## Docker (optional, for packaging evidence)

The same app as one container, with PostgreSQL:

```powershell
docker compose -f docker-compose.full.yml up --build
docker compose -f docker-compose.full.yml exec app python -m app.seed
# open http://localhost:8080
```

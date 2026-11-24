# Deploying ClaimSense to Azure: Container Registry + Linux VM

**Why this route:** the training sandbox's policy (effect: *Deny*) allows virtual machines, Container Registry and
AKS, but **not** App Service or Azure Database for PostgreSQL. So ClaimSense runs as **containers on an Azure VM**:
the app image is built and stored in **Azure Container Registry**, and the VM runs it with PostgreSQL in a second
container, exactly like `docker-compose.full.yml` on a laptop. (`deploy/DEPLOY.md` describes the App Service route
for an unrestricted subscription.)

```
laptop ──az acr build──> Azure Container Registry (claimsense image)
                                   │ docker pull
Browser ──http :80──> Azure VM (Ubuntu + Docker)
                         ├── app container  (FastAPI + React, from the registry)
                         └── db container   (PostgreSQL 16, data on a Docker volume)
                         └──> Azure OpenAI · Azure AI Search · Document Intelligence
```

About 60 minutes. Use the **same resource group** and a region **without** the "Region lock" error (South India
worked) for everything. Run Windows commands in **PowerShell**.

---

## 1 · Create the Container Registry (3 min)

Portal → *Create a resource* → **Container Registry** → Create.

| Setting | Value |
|---|---|
| Registry name | `claimsenseacryourname` (letters and digits only, unique) |
| Location | the allowed region |
| Pricing plan | **Basic** |

After it's created: registry → **Settings → Access keys** → turn on **Admin user**. Note the **username** and a
**password**.

## 2 · Build and push the image (5–8 min; do step 3 meanwhile)

From the `claimsense` folder (Azure CLI installed, `az login` done):

```powershell
az acr build --registry claimsenseacryourname --image claimsense:latest --image claimsense:v1 .
```

Azure uploads the source (without `.env`, `node_modules` or databases: see `.dockerignore`), builds it with the
`Dockerfile` and stores the image. Check: registry → **Services → Repositories → claimsense** shows `latest` and `v1`.

*No Azure CLI?* With Docker Desktop: `docker build -t claimsenseacryourname.azurecr.io/claimsense:latest .`, then
`docker login claimsenseacryourname.azurecr.io` (admin username/password) and
`docker push claimsenseacryourname.azurecr.io/claimsense:latest`.

## 3 · Create the VM (5 min clicking, 2–3 min waiting)

Portal → *Create a resource* → **Virtual machine** → Create.

| Setting | Value |
|---|---|
| Virtual machine name | `claimsense-vm` |
| Region | the allowed region |
| Image | **Ubuntu Server 24.04 LTS** (or 22.04) |
| Size | **Standard_B2s** (2 vCPU, 4 GiB). If not offered, the next small size (B2ms, D2s_v5) |
| Authentication type | **Password** |
| Username | `azureuser` |
| Password | a strong password (write it down) |
| Public inbound ports | **Allow selected ports**: **HTTP (80)** and **SSH (22)** |

Leave Disks and Networking at their defaults. Review + create → Create. When done, copy the VM's **Public IP address**
from its Overview page.

## 4 · Install Docker on the VM (5 min)

```powershell
ssh azureuser@VM-IP
```
Answer `yes` to the fingerprint question, enter the password. Then on the VM:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit
```
(`exit` and reconnect so the docker group applies.)

## 5 · Copy the settings to the VM (3 min)

On your **laptop**, from the `claimsense` folder:

```powershell
ssh azureuser@VM-IP "mkdir -p ~/claimsense"
scp docker-compose.vm.yml azureuser@VM-IP:~/claimsense/
scp backend/.env azureuser@VM-IP:~/claimsense/.env
```

Then on the **VM** add the registry name and a database password to that `.env`:

```bash
ssh azureuser@VM-IP
cd ~/claimsense
echo "ACR=claimsenseacryourname" >> .env
echo "DB_PASSWORD=ChooseADbPassword123" >> .env
```

The `.env` holds your Azure keys: it lives only on the VM and your laptop, never in the image or GitHub.

## 6 · Start ClaimSense (3 min)

On the VM, in `~/claimsense`:

```bash
docker login claimsenseacryourname.azurecr.io -u claimsenseacryourname -p 'ADMIN-PASSWORD'
docker compose -f docker-compose.vm.yml up -d
docker compose -f docker-compose.vm.yml ps
```
Both `db` and `app` should be *running* (the app waits for the database to be healthy).
Logs: `docker compose -f docker-compose.vm.yml logs -f app` (Ctrl+C to stop following).

## 7 · Load the data (1 min, or 10–15 min live)

```bash
docker compose -f docker-compose.vm.yml exec app python -m app.seed          # instant
# or with real Azure extraction and briefings:
# docker compose -f docker-compose.vm.yml exec app python -m app.seed --live
```
The policy index in Azure AI Search is already built and shared.

## 8 · Smoke test (10 min)

| Check | Expected |
|---|---|
| `http://VM-IP/health` | `{"status":"ok"}` |
| `http://VM-IP/api/health` | `azure:gpt-4.1-mini`, `azure_ai_search_hybrid`, `azure-docintel:prebuilt-read` |
| `http://VM-IP` | sign-in page; sign in as `reviewer01` (your `DEMO_PASSWORD`) |
| Claims queue, a HIGH claim, New claim → upload → verify, Monitoring | all work with live Azure calls |
| Reload on any page | stays on that page, still signed in |

## 9 · Load test the live app (5 min)

From your laptop, `claimsense\backend`, venv active:

```powershell
python -m app.load_test --url http://VM-IP/api --users 20 --duration 60
```

## 10 · Turn on CD (10 min)

GitHub repo → **Settings → Secrets and variables → Actions**:
- Variables: `ACR_NAME` = registry name, `VM_HOST` = VM public IP, `VM_USER` = `azureuser`
- Secrets: `ACR_USERNAME`, `ACR_PASSWORD` (registry admin), `VM_PASSWORD`

From then on, every push to `main`: tests → frontend build → **build and push the image to the registry** (tagged with
the commit) → **SSH to the VM, pull and restart** → health check. Run it once from *Actions → ci-cd → Run workflow*.

---

## If something goes wrong

| Symptom | Fix |
|---|---|
| Portal: "Region lock" | Pick the region that worked (South India) |
| Portal: VM size not allowed / unavailable | Choose another small size (B2ms, D2s_v5, B2als_v2) |
| `az acr build` fails | Read the build log it prints; send the error. Fallback: build with Docker Desktop and push |
| `http://VM-IP` doesn't load | VM → Networking: an inbound rule allowing port 80 must exist; `docker compose ps` shows app running |
| App keeps restarting | `docker compose -f docker-compose.vm.yml logs app` (usually a missing setting in `.env`) |
| `unauthorized` when pulling | Repeat the `docker login` in step 6 |
| DB password error after changing `DB_PASSWORD` | The volume keeps the first password: put it back, or reset with `docker compose ... down -v` (deletes data) |
| Sign-in fails | Password is `DEMO_PASSWORD` from the `.env` you copied |

## Notes for the assessment

- **Blocker recorded:** the sandbox policy denies `Microsoft.Web/sites` (App Service) and
  `Microsoft.DBforPostgreSQL/flexibleServers`; the deployment uses allowed services only.
- The site is plain HTTP on a public IP (no domain or TLS certificate): fine for a demo on synthetic data; production
  would add a domain, HTTPS and restrict SSH to known IP addresses.
- **Cost:** stop (deallocate) the VM when not in use; delete the VM, its disk, IP and the registry after the assessment.

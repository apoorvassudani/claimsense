"""Turn backend/.env into App Service settings, ready to paste into the portal.

Run from the claimsense folder:
    python deploy/env_to_appsettings.py "postgresql+psycopg://USER:PASSWORD@SERVER.postgres.database.azure.com:5432/postgres?sslmode=require"

Writes deploy/appsettings.json. In the portal: your Web App > Settings > Environment variables >
App settings > Advanced edit, then paste the file's contents (or: az webapp config appsettings set
--resource-group RG --name APP --settings @deploy/appsettings.json).

The file contains your secrets: it is git-ignored. Delete it after use.
"""
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "backend" / ".env"
OUT = ROOT / "deploy" / "appsettings.json"
DROP = {"DATABASE_URL", "LOG_FILE", "CORS_ORIGINS", "SIMULATE_FAILURE", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"}


def main() -> None:
    if len(sys.argv) < 2 or "postgres" not in sys.argv[1]:
        sys.exit(__doc__)
    values = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k.strip() not in DROP and v.strip():
                values[k.strip()] = v.strip().strip('"').strip("'")
    values.update({
        "DATABASE_URL": sys.argv[1],
        "LOG_FILE": "/home/LogFiles/claimsense.jsonl",   # persists across restarts
        "SCM_DO_BUILD_DURING_DEPLOYMENT": "true",        # App Service runs pip install on deploy
        # Fresh values for the cloud, different from your laptop:
        "AUTH_SECRET": secrets.token_urlsafe(48),
    })
    if "DEMO_PASSWORD" not in values:
        values["DEMO_PASSWORD"] = secrets.token_urlsafe(10)
    if values.get("LLM_PROVIDER") != "azure":
        print("Warning: LLM_PROVIDER is not 'azure' in backend/.env; the cloud app would use", values.get("LLM_PROVIDER"))
    OUT.write_text(json.dumps([{"name": k, "value": v, "slotSetting": False} for k, v in sorted(values.items())],
                              indent=2), encoding="utf-8")
    print(f"Wrote {len(values)} settings to {OUT}")
    print(f"Cloud sign-in password (DEMO_PASSWORD): {values['DEMO_PASSWORD']}")
    print("Paste the file into Advanced edit, save, then delete the file.")


if __name__ == "__main__":
    main()

"""Build the zip that Azure App Service runs (frontend + backend in one app).

Run from the claimsense folder with your venv active:
    python deploy/make_package.py

Creates deploy/claimsense-app.zip containing:
    requirements.txt          (App Service installs these during deployment)
    backend/app/...           (the API)
    data/policy_wording/...   (policy clauses for local keyword fallback)
    frontend/dist/...         (the built React app, calling the API at /api)
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deploy" / "claimsense-app.zip"
SKIP = {"__pycache__", ".pytest_cache", "logs"}


def build_frontend() -> None:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        sys.exit("npm not found. Install Node.js, then try again.")
    front = ROOT / "frontend"
    if not (front / "node_modules").is_dir():
        subprocess.run([npm, "install"], cwd=front, check=True)
    print("Building the frontend (VITE_API_URL=/api from .env.production) ...")
    subprocess.run([npm, "run", "build"], cwd=front, check=True)


def add_tree(z: zipfile.ZipFile, src: Path, arc_prefix: str) -> int:
    n = 0
    for p in sorted(src.rglob("*")):
        if p.is_file() and not (SKIP & set(p.parts)) and p.suffix != ".pyc":
            z.write(p, f"{arc_prefix}/{p.relative_to(src).as_posix()}")  # forward slashes for Linux
            n += 1
    return n


def main() -> None:
    build_frontend()
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        sys.exit("Frontend build failed: frontend/dist/index.html not found.")
    OUT.unlink(missing_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "backend" / "requirements.txt", "requirements.txt")
        files = add_tree(z, ROOT / "backend" / "app", "backend/app")
        files += add_tree(z, ROOT / "data" / "policy_wording", "data/policy_wording")
        files += add_tree(z, dist, "frontend/dist")
    print(f"Created {OUT} ({files + 1} files, {OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

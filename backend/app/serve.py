"""Production entry point: one server for the API and the built React app.

  /api/...   the FastAPI app (same routes as in development, e.g. /api/claims, /api/docs)
  /...       the built frontend (index.html, assets); unknown paths return index.html so
             React routes like /claims/12 work after a page refresh

Run:  uvicorn app.serve:root          (from backend/, after building the frontend)
The frontend must be built with VITE_API_URL=/api (frontend/.env.production does this).
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .main import app as api
from .main import lifespan

ROOT = Path(__file__).resolve().parents[2]
DIST = Path(os.getenv("FRONTEND_DIST", ROOT / "frontend" / "dist"))

# Mounted apps don't run their own startup, so the parent runs the same one
# (create tables, demo accounts).
root = FastAPI(title="ClaimSense", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
root.mount("/api", api)


@root.get("/health", include_in_schema=False)
def health():
    """Platform health probe (no sign-in needed)."""
    return {"status": "ok"}


if (DIST / "assets").is_dir():
    root.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@root.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if not (DIST / "index.html").is_file():
        return JSONResponse({"detail": f"Frontend not built: {DIST / 'index.html'} not found"}, status_code=503)
    file = (DIST / path).resolve()
    if path and file.is_file() and DIST.resolve() in file.parents:  # real file, inside dist only
        return FileResponse(file)
    return FileResponse(DIST / "index.html")

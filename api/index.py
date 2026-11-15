"""Vercel entry point: the FastAPI app as one Python function.

The dashboard is served by Vercel as static files (frontend/dist); /api/* and /media/* are rewritten here
(vercel.json). Writing and rendering never run on Vercel: set WORKER_MODE=github so the GitHub Actions render farm
does them, with Supabase as the shared database and video storage. See docs/DEPLOY-VERCEL.md.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INTERNAL_SCHEDULER", "0")      # no background threads on serverless; Vercel Cron instead
os.environ.setdefault("WORKER_MODE", "github")

from app.main import app  # noqa: E402,F401

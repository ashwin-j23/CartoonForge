"""Runtime configuration.

Everything comes from environment variables so the same code runs on a laptop, Render/Docker and the
GitHub Actions render farm. Keys can also be saved from the dashboard (encrypted in the `settings` table);
dashboard values win over env.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Read KEY=value lines from .env (project root, then backend/). Real environment variables always win.
    CARTOONFORGE_NO_DOTENV=1 skips it (tests: never touch the real database, keys or YouTube)."""
    if os.getenv("CARTOONFORGE_NO_DOTENV") == "1":
        return
    for f in (ROOT.parent / ".env", ROOT / ".env"):
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().removeprefix("export ").strip(), v.strip()
            if " #" in v and not v.startswith(("'", '"')):
                v = v.split(" #", 1)[0].strip()              # inline comment
            v = v.strip("'\"")
            if k and v and k not in os.environ:
                os.environ[k] = v


_load_dotenv()
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
DATA_DIR = Path(os.getenv("DATA_DIR") or ("/tmp/cartoonforge" if os.getenv("VERCEL") else ROOT / "data")).resolve()
MEDIA_DIR = DATA_DIR / "media"
WORK_DIR = DATA_DIR / "work"
for _d in (DATA_DIR, MEDIA_DIR, WORK_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", ROOT.parent / "frontend" / "dist"))


def _ffmpeg() -> str:
    import shutil
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return "ffmpeg"


FFMPEG = _ffmpeg()


def env(name: str, default: str = "") -> str:
    v = (os.getenv(name) or "").strip()
    return v or default


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


ON_VERCEL = bool(os.getenv("VERCEL"))
IS_PROD = env("ENV") == "production" or bool(os.getenv("RENDER")) or bool(os.getenv("GITHUB_ACTIONS")) or ON_VERCEL
# serverless: no background threads (Vercel Cron calls /api/cron/tick); rendering goes to the GitHub render farm
INTERNAL_SCHEDULER = env("INTERNAL_SCHEDULER", "0" if ON_VERCEL else "1")
CORS_ORIGINS = [x.strip() for x in env("CORS_ORIGINS").split(",") if x.strip()]
WEAK_VALUES = {"", "change-me", "admin", "password", "secret", "kids", "123456"}


def _dev_value(name: str, n: int) -> str:
    """Laptop runs get random values saved in the data dir (never in the repo)."""
    import secrets as _s
    f = DATA_DIR / f".dev_{name}"
    if not f.exists():
        f.write_text(_s.token_urlsafe(n))
        f.chmod(0o600)
    return f.read_text().strip()


ADMIN_PASSWORD = env("ADMIN_PASSWORD") or ("" if IS_PROD else _dev_value("admin_password", 12))
SECRET_KEY = env("SECRET_KEY") or ("" if IS_PROD else _dev_value("secret_key", 48))
CRON_SECRET = env("CRON_SECRET", "")
TOKEN_DAYS = env_int("TOKEN_DAYS", 7)


def check_security(for_web: bool = True) -> list[str]:
    probs = []
    if for_web:
        if ADMIN_PASSWORD.lower() in WEAK_VALUES or len(ADMIN_PASSWORD) < 12:
            probs.append("ADMIN_PASSWORD must be set and at least 12 characters.")
        if CRON_SECRET and len(CRON_SECRET) < 16:
            probs.append("CRON_SECRET must be at least 16 random characters.")
    if SECRET_KEY in WEAK_VALUES or len(SECRET_KEY) < 32:
        probs.append("SECRET_KEY must be 32+ random characters.")
    return probs


PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "").rstrip("/")
if PUBLIC_BASE_URL and not PUBLIC_BASE_URL.startswith("http"):
    PUBLIC_BASE_URL = "https://" + PUBLIC_BASE_URL

# inline -> render inside the web process; github -> dispatch the GitHub Actions render farm
WORKER_MODE = env("WORKER_MODE", "github" if ON_VERCEL else "inline")
GITHUB_REPO = re.sub(r"^(https?://)?(www\.)?github\.com/", "", env("GITHUB_REPO", "")).strip("/").removesuffix(".git")
GITHUB_TOKEN = env("GITHUB_TOKEN", "")
GITHUB_WORKFLOW = env("GITHUB_WORKFLOW", "worker.yml")
GITHUB_REF = env("GITHUB_REF_NAME", "main")

SUPABASE_URL = env("SUPABASE_URL").rstrip("/")
SUPABASE_SERVICE_KEY = env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = env("SUPABASE_BUCKET", "episodes")


def supabase_headers(key: str = "") -> dict:
    key = key or SUPABASE_SERVICE_KEY
    h = {"apikey": key}
    if not key.startswith("sb_"):
        h["Authorization"] = f"Bearer {key}"
    return h


# --- render: long-form landscape YouTube (16:9). 24 fps is the classic cartoon rate and renders 20% faster.
RENDER_WIDTH = env_int("RENDER_WIDTH", 1920)
RENDER_HEIGHT = env_int("RENDER_HEIGHT", 1080)
RENDER_FPS = env_int("RENDER_FPS", 24)
def _auto_workers() -> int:
    """One render worker per CPU, but never more than free memory allows (~0.9 GB each at 1080p supersampled)."""
    cpus = os.cpu_count() or 2
    try:
        avail_kb = next(int(l.split()[1]) for l in open("/proc/meminfo") if l.startswith("MemAvailable"))
        by_mem = max(1, int(avail_kb / 1024 / 1024 / 0.9))
    except (OSError, StopIteration, ValueError):
        by_mem = 4
    return max(1, min(cpus, by_mem, 12))


RENDER_WORKERS = env_int("RENDER_WORKERS", 0)       # 0 = automatic (decided at render time from free memory)
X264_PRESET = env("X264_PRESET", "faster")
X264_CRF = env_int("X264_CRF", 18)                 # 18 = visually lossless for flat cartoon colours

SECRET_KEYS = [
    "GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY", "CEREBRAS_API_KEY",
    "MISTRAL_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY",
    "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN",
    "FAL_KEY", "RUNWAY_API_KEY",           # AI animation: Kling via fal.ai, Runway Gen-4 (Gemini Omni uses GEMINI_API_KEY)
    "YOUTUBE_API_KEY",                     # plain API key: trend scan (hot kids videos), separate from the upload OAuth
]

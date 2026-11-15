import os
import secrets
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cartoonforge-test-"))
os.environ.setdefault("TTS_ENGINE", "espeak")
os.environ.setdefault("KOKORO_ENABLED", "0")
os.environ.setdefault("INTERNAL_SCHEDULER", "0")
# CI (GITHUB_ACTIONS) counts as production, which refuses to start without these: random throwaway values per run
os.environ.setdefault("ADMIN_PASSWORD", secrets.token_urlsafe(18))
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

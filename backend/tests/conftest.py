import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cartoonforge-test-"))
os.environ.setdefault("TTS_ENGINE", "espeak")
os.environ.setdefault("KOKORO_ENABLED", "0")
os.environ.setdefault("INTERNAL_SCHEDULER", "0")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

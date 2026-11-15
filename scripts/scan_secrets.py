#!/usr/bin/env python3
"""Fail if anything that looks like a real key, token or cookie file is about to be committed.

    python scripts/scan_secrets.py            # scan files tracked or staged by git
    python scripts/scan_secrets.py --all      # scan every file in the folder

Runs in CI (.github/workflows/ci.yml) and as a git pre-commit hook (scripts/install_hooks.sh).
It prints file and line only - never the matched value.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS = {
    "Google / Gemini API key": r"AIza[0-9A-Za-z_\-]{35}",
    "OpenAI key": r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{32,}",
    "Anthropic key": r"sk-ant-[A-Za-z0-9_\-]{32,}",
    "Groq key": r"gsk_[A-Za-z0-9]{40,}",
    "NVIDIA key": r"nvapi-[A-Za-z0-9_\-]{40,}",
    "OpenRouter key": r"sk-or-v1-[a-f0-9]{48,}",
    "ElevenLabs key": r"(?i)xi-api-key['\"]?\s*[:=]\s*['\"][a-f0-9]{32}",
    "Facebook / Instagram token": r"EAA[A-Za-z0-9]{60,}",
    "GitHub token": r"(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}",
    "Google OAuth secret": r"GOCSPX-[A-Za-z0-9_\-]{20,}",
    "Google refresh token": r"1//0[A-Za-z0-9_\-]{40,}",
    "Supabase secret key": r"sb_secret_[A-Za-z0-9_\-]{20,}",
    "JWT (Supabase service key?)": r"eyJhbGciOi[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}",
    "Slack token": r"xox[abprs]-[A-Za-z0-9\-]{20,}",
    "Private key block": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "Password assigned in code": r"(?i)(?:admin_?password|passwd|password)\s*[:=]\s*['\"](?!\s*['\"])(?![<{$])[^'\"\s]{4,}['\"]",
}
BAD_NAMES = re.compile(r"(^|/)(\.env(\..+)?|cookies?\.txt|.*cookies.*\.txt|accounts\.json|client_secret.*\.json|token.*\.json|.*\.pem)$")
ALLOWED_NAMES = {".env.example"}
SKIP_DIRS = {"node_modules", ".git", "dist", "__pycache__", ".venv", "data"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".mp3", ".mp4", ".wav", ".otf", ".ttf", ".woff", ".woff2", ".zip", ".onnx", ".bin", ".ico"}
# Lines that mention a pattern on purpose (this file, tests with fake values).
ALLOW_MARK = "scan-secrets: allow"


def files(all_files: bool) -> list[Path]:
    if not all_files:
        try:
            out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True,
                                 text=True, check=True).stdout.split("\n")
            return [ROOT / f for f in out if f]
        except Exception:
            pass
    return [p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS)]


def scan(paths: list[Path]) -> list[str]:
    hits = []
    compiled = {k: re.compile(v) for k, v in PATTERNS.items()}
    for p in paths:
        rel = p.relative_to(ROOT).as_posix()
        if p.name not in ALLOWED_NAMES and BAD_NAMES.search(rel):
            hits.append(f"{rel}: this kind of file must never be committed (secrets / cookies)")
            continue
        if p.suffix.lower() in SKIP_EXT or p.name == Path(__file__).name or not p.exists():
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if ALLOW_MARK in line:
                continue
            for name, rx in compiled.items():
                if rx.search(line):
                    hits.append(f"{rel}:{n}: looks like a {name}")
    return hits


if __name__ == "__main__":
    found = scan(files("--all" in sys.argv))
    if found:
        print("Possible secrets found - remove them, rotate the key, and use environment variables:")
        print("\n".join("  " + h for h in found))
        sys.exit(1)
    print("No secrets found.")

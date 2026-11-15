"""Media storage: Supabase Storage (public bucket) or local disk.

Supabase's free plan refuses files over 50 MB, and a 1080p episode is bigger. A large video is therefore stored
as (1) its full-quality bytes in 45 MB parts + a small manifest, and (2) a 540p preview under the limit at the
normal key, so players keep working. fetch() joins the parts back into the exact original for YouTube, Shorts
and compilations.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from . import config


def _public_local(key: str) -> str:
    return f"{config.PUBLIC_BASE_URL}/media/{key}" if config.PUBLIC_BASE_URL else f"/media/{key}"


PART_BYTES = int(float(config.env("STORAGE_PART_MB", "45")) * 1_000_000)   # under Supabase free's 50 MB/file


def _supabase() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY)


def _upload_bytes(data: bytes, key: str, content_type: str) -> None:
    url = f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}/{key}"
    r = httpx.post(url, content=data, timeout=300, headers={
        **config.supabase_headers(),
        "Content-Type": content_type, "x-upsert": "true", "cache-control": "max-age=31536000"})
    if r.status_code >= 400:
        raise RuntimeError(f"Storage upload failed {r.status_code}: {r.text[:200]}")


def _preview(local: Path, limit: int) -> Path:
    """A 540p copy under `limit` bytes for the dashboard player (the full file is kept in parts)."""
    from .render.episode import probe_duration
    out = Path(tempfile.mkstemp(suffix=".mp4", dir=config.WORK_DIR)[1])
    secs = max(1.0, probe_duration(local))
    base = [config.FFMPEG, "-y", "-loglevel", "error", "-i", str(local), "-vf", "scale=-2:540",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "-preset", "veryfast"]
    subprocess.run(base + ["-crf", "28", str(out)], check=True)
    if out.stat().st_size > limit:                       # long episode: fit the size exactly with a bitrate
        kbps = max(150, int(limit * 8 * 0.92 / secs / 1000) - 96)
        subprocess.run(base + ["-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k", str(out)],
                       check=True)
    return out


def put(local: Path, key: str, content_type: str) -> str:
    """Store a file and return its URL (public URL when Supabase is used)."""
    if _supabase():
        local = Path(local)
        size = local.stat().st_size
        if size > PART_BYTES and content_type.startswith("video/"):
            n = 0
            with open(local, "rb") as f:
                while chunk := f.read(PART_BYTES):
                    _upload_bytes(chunk, f"{key}.part{n:03d}", "application/octet-stream")
                    n += 1
            _upload_bytes(json.dumps({"parts": n, "size": size, "part_bytes": PART_BYTES}).encode(),
                          f"{key}.parts.json", "application/octet-stream")
            prev = _preview(local, PART_BYTES)
            try:
                _upload_bytes(prev.read_bytes(), key, content_type)
            finally:
                prev.unlink(missing_ok=True)
        else:
            _upload_bytes(local.read_bytes(), key, content_type)
        return key_url(key)
    dest = config.MEDIA_DIR / key
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    shutil.copyfile(local, dest)
    return _public_local(key)


UPLOAD_MAX_MB = int(config.env("UPLOAD_MAX_MB", "50"))     # Supabase free plan: 50 MB per file


def signed_upload(key: str) -> dict:
    """A one-time URL the browser PUTs a file to directly (Vercel caps request bodies at 4.5 MB)."""
    if not (config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY):
        raise RuntimeError("Direct uploads need Supabase storage (set SUPABASE_URL and SUPABASE_SERVICE_KEY)")
    r = httpx.post(f"{config.SUPABASE_URL}/storage/v1/object/upload/sign/{config.SUPABASE_BUCKET}/{key}",
                   json={}, timeout=30, headers={**config.supabase_headers(), "x-upsert": "true"})
    if r.status_code >= 400:
        raise RuntimeError(f"Could not start the upload ({r.status_code}): {r.text[:200]}")
    return {"key": key, "upload_url": f"{config.SUPABASE_URL}/storage/v1{r.json()['url']}",
            "public_url": key_url(key), "max_mb": UPLOAD_MAX_MB}


AUDIO_TYPES = ["audio/mpeg", "audio/mp3", "audio/mp4", "audio/x-m4a", "audio/aac", "audio/wav", "audio/x-wav",
               "audio/wave", "audio/ogg"]
VIDEO_TYPES = ["video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/x-m4v",
               "application/octet-stream"]          # phones send .MOV as video/quicktime; some browsers send no type
UPLOAD_TYPES = AUDIO_TYPES + VIDEO_TYPES


def allow_uploads() -> None:
    """The bucket may only accept a few types; add the ones the upload form offers (other settings kept)."""
    base = f"{config.SUPABASE_URL}/storage/v1/bucket/{config.SUPABASE_BUCKET}"
    r = httpx.get(base, timeout=20, headers=config.supabase_headers())
    if r.status_code >= 400:
        return
    b = r.json()
    allowed = b.get("allowed_mime_types")
    if not allowed or all(t in allowed for t in UPLOAD_TYPES):
        return                      # no restriction, or already allowed
    httpx.put(base, timeout=20, headers=config.supabase_headers(), json={
        "public": b.get("public", True), "file_size_limit": b.get("file_size_limit"),
        "allowed_mime_types": allowed + [t for t in UPLOAD_TYPES if t not in allowed]})


def key_url(key: str) -> str:
    if config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY:
        return f"{config.SUPABASE_URL}/storage/v1/object/public/{config.SUPABASE_BUCKET}/{key}"
    return _public_local(key)


def _manifest(url: str) -> dict | None:
    """The parts manifest of a large video, or None for a normal single file."""
    try:
        r = httpx.get(url + ".parts.json", timeout=30, follow_redirects=True)
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def remove(keys: list[str]) -> None:
    if not keys:
        return
    if _supabase():
        extra = []
        for k in keys:
            if k.endswith(".mp4") and (m := _manifest(key_url(k))):
                extra += [f"{k}.part{i:03d}" for i in range(int(m.get("parts", 0)))] + [f"{k}.parts.json"]
        keys = list(keys) + extra
        httpx.request("DELETE", f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}",
                      json={"prefixes": keys}, timeout=60, headers={
                          **config.supabase_headers()})
        return
    for k in keys:
        (config.MEDIA_DIR / k).unlink(missing_ok=True)


def fetch(url_or_key: str) -> Path:
    """Get a local path for a stored video (downloads from Supabase if needed)."""
    if url_or_key.startswith("/media/") or (config.PUBLIC_BASE_URL and url_or_key.startswith(config.PUBLIC_BASE_URL + "/media/")):
        key = url_or_key.split("/media/", 1)[1]
        return config.MEDIA_DIR / key
    tmp = Path(tempfile.mkstemp(suffix=".mp4", dir=config.WORK_DIR)[1])
    m = _manifest(url_or_key)                            # large video: join the full-quality parts
    urls = [f"{url_or_key}.part{i:03d}" for i in range(int(m["parts"]))] if m else [url_or_key]
    with open(tmp, "wb") as f:
        for u in urls:
            with httpx.stream("GET", u, timeout=300, follow_redirects=True) as r:
                r.raise_for_status()
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
    if m and tmp.stat().st_size != int(m.get("size", -1)):
        raise RuntimeError(f"Video parts incomplete: {tmp.stat().st_size} of {m.get('size')} bytes")
    return tmp


def public_url(url: str) -> str:
    """Instagram must be able to download the file itself -> needs an absolute public URL."""
    if url.startswith("http"):
        return url
    if not config.PUBLIC_BASE_URL:
        raise RuntimeError("Instagram needs a public video URL: configure Supabase, or set PUBLIC_BASE_URL.")
    return config.PUBLIC_BASE_URL + url

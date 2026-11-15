"""Media storage: Supabase Storage (public bucket) or local disk."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import httpx

from . import config


def _public_local(key: str) -> str:
    return f"{config.PUBLIC_BASE_URL}/media/{key}" if config.PUBLIC_BASE_URL else f"/media/{key}"


def put(local: Path, key: str, content_type: str) -> str:
    """Store a file and return its URL (public URL when Supabase is used)."""
    if config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY:
        url = f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}/{key}"
        with open(local, "rb") as f:
            r = httpx.post(url, content=f.read(), timeout=300, headers={
                **config.supabase_headers(),
                "Content-Type": content_type, "x-upsert": "true", "cache-control": "max-age=31536000"})
        if r.status_code >= 400:
            raise RuntimeError(f"Storage upload failed {r.status_code}: {r.text[:200]}")
        return f"{config.SUPABASE_URL}/storage/v1/object/public/{config.SUPABASE_BUCKET}/{key}"
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


def remove(keys: list[str]) -> None:
    if not keys:
        return
    if config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY:
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
    with httpx.stream("GET", url_or_key, timeout=300, follow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 16):
                f.write(chunk)
    return tmp


def public_url(url: str) -> str:
    """Instagram must be able to download the file itself -> needs an absolute public URL."""
    if url.startswith("http"):
        return url
    if not config.PUBLIC_BASE_URL:
        raise RuntimeError("Instagram needs a public video URL: configure Supabase, or set PUBLIC_BASE_URL.")
    return config.PUBLIC_BASE_URL + url

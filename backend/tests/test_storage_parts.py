"""Large videos on Supabase's free plan: full quality in parts + a small preview; fetch() rejoins them exactly."""
import json
import os
import subprocess
import types

import httpx
import pytest

from app import config, storage

LIMIT = 50_000          # the fake bucket's per-file limit (stands in for Supabase free's 50 MB)


@pytest.fixture
def bucket(monkeypatch, tmp_path):
    files: dict[str, bytes] = {}
    pub = "/storage/v1/object/public/episodes/"
    put_prefix = "/storage/v1/object/episodes/"

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if req.method == "POST" and path.startswith(put_prefix):
            if len(req.content) > LIMIT:
                return httpx.Response(400, json={"statusCode": "413", "error": "Payload too large"})
            files[path[len(put_prefix):]] = req.content
            return httpx.Response(200, json={"Key": path})
        if req.method == "GET" and path.startswith(pub):
            k = path[len(pub):]
            return httpx.Response(200, content=files[k]) if k in files else httpx.Response(404)
        if req.method == "DELETE":
            for k in json.loads(req.content)["prefixes"]:
                files.pop(k, None)
            return httpx.Response(200, json=[])
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fake = types.SimpleNamespace(get=client.get, post=client.post, stream=client.stream, request=client.request,
                                 HTTPError=httpx.HTTPError)
    monkeypatch.setattr(storage, "httpx", fake)
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_SERVICE_KEY", "test")
    monkeypatch.setattr(config, "SUPABASE_BUCKET", "episodes")
    monkeypatch.setattr(storage, "PART_BYTES", LIMIT - 5_000)
    return files


def test_large_video_is_split_and_rejoined_exactly(bucket, monkeypatch, tmp_path):
    big = tmp_path / "episode.mp4"
    data = os.urandom(170_000)
    big.write_bytes(data)
    small = tmp_path / "preview.mp4"
    small.write_bytes(b"preview" * 100)
    monkeypatch.setattr(storage, "_preview", lambda local, limit: small)

    url = storage.put(big, "ep1/episode.mp4", "video/mp4")
    assert url.endswith("/public/episodes/ep1/episode.mp4")
    assert bucket["ep1/episode.mp4"] == b"preview" * 100      # players get the small preview
    parts = sorted(k for k in bucket if ".part0" in k)
    assert len(parts) == 4 and all(len(bucket[k]) <= LIMIT for k in bucket)
    assert json.loads(bucket["ep1/episode.mp4.parts.json"])["size"] == len(data)

    got = storage.fetch(url)
    assert got.read_bytes() == data                          # YouTube gets the full-quality original

    storage.remove(["ep1/episode.mp4"])
    assert bucket == {}


def test_small_files_stay_single(bucket, tmp_path):
    f = tmp_path / "thumb.jpg"
    f.write_bytes(b"x" * 1000)
    url = storage.put(f, "ep1/thumb.jpg", "image/jpeg")
    assert list(bucket) == ["ep1/thumb.jpg"]
    assert storage.fetch(url).read_bytes() == b"x" * 1000


def test_preview_fits_the_limit(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run([config.FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=24",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libx264", "-crf", "8",
                    "-c:a", "aac", "-shortest", str(src)], check=True)
    limit = src.stat().st_size // 4
    out = storage._preview(src, limit)
    assert out.stat().st_size <= limit

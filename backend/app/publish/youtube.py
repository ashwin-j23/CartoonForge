"""YouTube uploads via the official Data API v3 (OAuth refresh token).

Every upload is declared made-for-kids (COPPA). YouTube then switches off comments, the notification bell,
cards/end screens and personalised ads on it — the show is designed around that (no comment prompts)."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

import httpx

from ..settings import save_secrets, secret

SCOPES = ("https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly "
          "https://www.googleapis.com/auth/youtube.force-ssl https://www.googleapis.com/auth/yt-analytics.readonly")


def auth_url(redirect_uri: str, state: str) -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": secret("YT_CLIENT_ID"), "redirect_uri": redirect_uri, "response_type": "code",
        "scope": SCOPES, "access_type": "offline", "prompt": "consent", "state": state})


def exchange_code(code: str, redirect_uri: str, save: bool = True) -> str:
    """Refresh token for the channel that just signed in; saved as the main channel unless save=False."""
    r = httpx.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "code": code, "client_id": secret("YT_CLIENT_ID"), "client_secret": secret("YT_CLIENT_SECRET"),
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    r.raise_for_status()
    tok = r.json().get("refresh_token")
    if not tok:
        raise RuntimeError("Google did not return a refresh token (remove the app at myaccount.google.com/permissions and retry)")
    if save:
        save_secrets({"YT_REFRESH_TOKEN": tok})
    return tok


def _access_token(refresh_token: str = "") -> str:
    """Access token for the main channel, or for a network channel when its refresh token is given."""
    rt = refresh_token or secret("YT_REFRESH_TOKEN")
    if not (secret("YT_CLIENT_ID") and secret("YT_CLIENT_SECRET") and rt):
        raise RuntimeError("YouTube not connected (Channels → Connect YouTube)")
    r = httpx.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": secret("YT_CLIENT_ID"), "client_secret": secret("YT_CLIENT_SECRET"),
        "refresh_token": rt, "grant_type": "refresh_token"})
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube token refresh failed: {r.text[:200]}")
    return r.json()["access_token"]


def channel_info(refresh_token: str = "") -> dict:
    tok = _access_token(refresh_token)
    r = httpx.get("https://www.googleapis.com/youtube/v3/channels", timeout=30,
                  params={"part": "snippet,statistics", "mine": "true"}, headers={"Authorization": f"Bearer {tok}"})
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return {}
    c = items[0]
    return {"id": c["id"], "title": c["snippet"]["title"], "thumb": c["snippet"]["thumbnails"]["default"]["url"],
            "subscribers": int(c["statistics"].get("subscriberCount", 0)),
            "views": int(c["statistics"].get("viewCount", 0)), "videos": int(c["statistics"].get("videoCount", 0))}


def get_about(refresh_token: str = "") -> dict:
    """The channel's description and keywords (YouTube 'About')."""
    tok = _access_token(refresh_token)
    r = httpx.get("https://www.googleapis.com/youtube/v3/channels", timeout=30,
                  params={"part": "brandingSettings,snippet", "mine": "true"}, headers={"Authorization": f"Bearer {tok}"})
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel on this account")
    c = items[0]
    ch = (c.get("brandingSettings") or {}).get("channel") or {}
    return {"id": c["id"], "title": c["snippet"]["title"], "handle": c["snippet"].get("customUrl", ""),
            "description": ch.get("description", ""),
            "keywords": ch.get("keywords", ""), "branding": c.get("brandingSettings") or {}}


def set_about(description: str | None = None, refresh_token: str = "", **fields) -> dict:
    """Change channel settings: description and/or keywords, country, defaultLanguage, unsubscribedTrailer,
    bannerExternalUrl (image). brandingSettings is replaced as a whole, so every field not given is sent back
    unchanged. Costs 50 quota units."""
    cur = get_about(refresh_token)
    branding = dict(cur["branding"])
    channel = dict(branding.get("channel") or {})
    if description is not None:
        channel["description"] = description[:1000]
    for k in ("keywords", "country", "defaultLanguage", "unsubscribedTrailer"):
        if fields.get(k) is not None:
            channel[k] = fields[k]
    if fields.get("bannerExternalUrl"):
        branding["image"] = {**(branding.get("image") or {}), "bannerExternalUrl": fields["bannerExternalUrl"]}
    body = {"id": cur["id"], "brandingSettings": {**branding, "channel": channel}}
    r = httpx.put("https://www.googleapis.com/youtube/v3/channels", timeout=30, params={"part": "brandingSettings"},
                  headers={"Authorization": f"Bearer {_access_token(refresh_token)}"}, json=body)
    if r.status_code == 403 and "insufficient" in r.text.lower():
        raise PermissionError("YouTube needs permission to edit the channel: press Reconnect YouTube once.")
    r.raise_for_status()
    return {"description": channel.get("description", "")}


def _media_upload(url: str, data: bytes, ctype: str, refresh_token: str = "", params: dict | None = None) -> httpx.Response:
    r = httpx.post(url, params={"uploadType": "media", **(params or {})}, content=data, timeout=120,
                   headers={"Authorization": f"Bearer {_access_token(refresh_token)}", "Content-Type": ctype})
    if r.status_code == 403 and "insufficient" in r.text.lower():
        raise PermissionError("YouTube needs permission to edit the channel: press Reconnect YouTube once.")
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube {r.status_code}: {r.text[:200]}")
    return r


def set_banner(data: bytes, ctype: str, refresh_token: str = "") -> str:
    """Upload a channel banner (at least 2048x1152, 16:9, under 6 MB) and make it the channel's banner."""
    url = _media_upload("https://www.googleapis.com/upload/youtube/v3/channelBanners/insert", data, ctype,
                        refresh_token).json()["url"]
    set_about(None, refresh_token, bannerExternalUrl=url)
    return url


def set_watermark(data: bytes, ctype: str, refresh_token: str = "") -> None:
    """The small 'subscribe' image shown on every video (square, at least 150x150, under 1 MB), whole video."""
    cid = get_about(refresh_token)["id"]
    boundary = "cartoonforge-wm"
    meta = json.dumps({"timing": {"type": "offsetFromEnd", "offsetMs": 0, "durationMs": 0}, "position": {
        "type": "corner", "cornerPosition": "bottomRight"}, "targetChannelId": cid})
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            f"--{boundary}\r\nContent-Type: {ctype}\r\n\r\n").encode() + data + f"\r\n--{boundary}--".encode()
    r = httpx.post("https://www.googleapis.com/upload/youtube/v3/watermarks/set", timeout=60,
                   params={"channelId": cid, "uploadType": "multipart"}, content=body,
                   headers={"Authorization": f"Bearer {_access_token(refresh_token)}",
                            "Content-Type": f"multipart/related; boundary={boundary}"})
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube {r.status_code}: {r.text[:200]}")


def update_video(video_id: str, refresh_token: str = "", title: str | None = None, description: str | None = None,
                 privacy: str | None = None, tags: list[str] | None = None, made_for_kids: bool | None = None,
                 publish_at: str | None = None) -> dict:
    """Edit a live video. snippet/status are replaced whole, so the current values are read first."""
    tok = _access_token(refresh_token)
    h = {"Authorization": f"Bearer {tok}"}
    r = httpx.get("https://www.googleapis.com/youtube/v3/videos", timeout=30, headers=h,
                  params={"part": "snippet,status", "id": video_id})
    r.raise_for_status()
    items = r.json().get("items") or []
    if not items:
        raise RuntimeError("Video not found on YouTube (deleted?)")
    v = items[0]
    sn = {k: v["snippet"][k] for k in ("title", "description", "tags", "categoryId", "defaultLanguage",
                                       "defaultAudioLanguage") if k in v["snippet"]}
    st = {k: v["status"][k] for k in ("privacyStatus", "selfDeclaredMadeForKids", "containsSyntheticMedia",
                                      "license", "embeddable", "publicStatsViewable") if k in v["status"]}
    if title is not None:
        sn["title"] = title.strip()[:100]
    if description is not None:
        sn["description"] = description[:4900]
    if tags is not None:
        sn["tags"] = [t for t in tags if len(t) <= 40][:15]
    if privacy in ("public", "unlisted", "private"):
        st["privacyStatus"] = privacy
    if made_for_kids is not None:
        st["selfDeclaredMadeForKids"] = bool(made_for_kids)
    if publish_at:                               # schedule: YouTube makes a private video public at this time
        st["privacyStatus"], st["publishAt"] = "private", publish_at
    r = httpx.put("https://www.googleapis.com/youtube/v3/videos", timeout=30, headers=h, params={"part": "snippet,status"},
                  json={"id": video_id, "snippet": sn, "status": st})
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube {r.status_code}: {r.text[:200]}")
    return {"title": sn["title"], "privacy": st.get("privacyStatus")}


def retention(ids: list[str], refresh_token: str = "") -> dict:
    """{video id: {"avg_pct": % of the video watched on average, "avg_s": seconds}} from YouTube Analytics.
    Needs the yt-analytics.readonly scope (granted on the next Reconnect) and the API enabled in Google Cloud."""
    if not ids:
        return {}
    from datetime import date
    tok = _access_token(refresh_token)
    out = {}
    for i in range(0, len(ids), 200):
        r = httpx.get("https://youtubeanalytics.googleapis.com/v2/reports", timeout=30,
                      params={"ids": "channel==MINE", "startDate": "2025-01-01", "endDate": date.today().isoformat(),
                              "metrics": "averageViewPercentage,averageViewDuration", "dimensions": "video",
                              "filters": "video==" + ",".join(ids[i:i + 200])},
                      headers={"Authorization": f"Bearer {tok}"})
        r.raise_for_status()
        for vid, pct, sec in r.json().get("rows") or []:
            out[vid] = {"avg_pct": round(float(pct), 1), "avg_s": round(float(sec), 1)}
    return out


def audience_countries(days: int = 28, refresh_token: str = "") -> dict:
    """{country code: views} for the last `days` days (YouTube Analytics)."""
    from datetime import date, timedelta
    tok = _access_token(refresh_token)
    r = httpx.get("https://youtubeanalytics.googleapis.com/v2/reports", timeout=30,
                  params={"ids": "channel==MINE", "startDate": (date.today() - timedelta(days=days)).isoformat(),
                          "endDate": date.today().isoformat(), "metrics": "views", "dimensions": "country",
                          "sort": "-views", "maxResults": 25},
                  headers={"Authorization": f"Bearer {tok}"})
    r.raise_for_status()
    return {c: int(v) for c, v in r.json().get("rows") or []}


def retention_curve(video_id: str, refresh_token: str = "") -> list[tuple[float, float]]:
    """[(elapsed ratio 0..1, audience watch ratio)] — how many viewers are still watching at each point."""
    from datetime import date
    r = httpx.get("https://youtubeanalytics.googleapis.com/v2/reports", timeout=30,
                  params={"ids": "channel==MINE", "startDate": "2025-01-01", "endDate": date.today().isoformat(),
                          "metrics": "audienceWatchRatio", "dimensions": "elapsedVideoTimeRatio",
                          "filters": f"video=={video_id}"},
                  headers={"Authorization": f"Bearer {_access_token(refresh_token)}"})
    r.raise_for_status()
    return [(float(x), float(y)) for x, y in r.json().get("rows") or []]


def video_stats(ids: list[str], refresh_token: str = "") -> dict:
    if not ids:
        return {}
    tok = _access_token(refresh_token)
    out = {}
    for i in range(0, len(ids), 50):
        r = httpx.get("https://www.googleapis.com/youtube/v3/videos", timeout=30,
                      params={"part": "statistics", "id": ",".join(ids[i:i + 50])},
                      headers={"Authorization": f"Bearer {tok}"})
        r.raise_for_status()
        for v in r.json().get("items", []):
            st = v.get("statistics", {})
            out[v["id"]] = {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                            "comments": int(st.get("commentCount", 0))}
    return out


def upload(path: Path, title: str, description: str, tags: list[str], privacy: str = "public",
           thumb: Path | None = None, language: str = "en", localizations: dict | None = None,
           refresh_token: str = "", category_id: str = "27", made_for_kids: bool = True, synthetic: bool = False,
           short: bool = False, publish_at: str | None = None) -> dict:
    tok = _access_token(refresh_token)
    title = title.strip()[:100]
    if short and "#shorts" not in (title + description).lower():
        description = description.rstrip() + "\n\n#shorts"
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": bool(made_for_kids),
              "containsSyntheticMedia": bool(synthetic), "license": "youtube", "embeddable": True}
    if publish_at and privacy == "private":
        status["publishAt"] = publish_at          # YouTube publishes it itself at that time
    meta = {"snippet": {"title": title, "description": description[:4900], "tags": [t for t in tags if len(t) <= 40][:15],
                        "categoryId": str(category_id), "defaultLanguage": language, "defaultAudioLanguage": language},
            "status": status}
    parts = "snippet,status"
    if localizations:
        meta["localizations"] = localizations
        parts += ",localizations"
    size = path.stat().st_size
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
               "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}
    url = f"https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part={parts}"
    r = httpx.post(url, headers=headers, content=json.dumps(meta), timeout=60)
    if r.status_code == 400 and "containsSyntheticMedia" in r.text:
        meta["status"].pop("containsSyntheticMedia")
        r = httpx.post(url, headers=headers, content=json.dumps(meta), timeout=60)
    if r.status_code == 400 and "localizations" in r.text:      # a bad translation must not block the upload
        meta.pop("localizations", None)
        url = url.replace(",localizations", "")
        r = httpx.post(url, headers=headers, content=json.dumps(meta), timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube init failed {r.status_code}: {r.text[:300]}")
    loc = r.headers["Location"]
    # long-form files are big: upload in 16 MB chunks (resumable), never the whole file in memory
    chunk = 16 * 1024 * 1024
    with open(path, "rb") as f:
        sent = 0
        while sent < size:
            data = f.read(chunk)
            end_b = sent + len(data) - 1
            r = httpx.put(loc, content=data, timeout=600, headers={
                "Authorization": f"Bearer {tok}", "Content-Type": "video/mp4",
                "Content-Range": f"bytes {sent}-{end_b}/{size}"})
            if r.status_code in (200, 201):
                break
            if r.status_code != 308:
                raise RuntimeError(f"YouTube upload failed {r.status_code}: {r.text[:300]}")
            rng = r.headers.get("Range")
            sent = int(rng.split("-")[1]) + 1 if rng else end_b + 1
            f.seek(sent)
    vid = r.json()["id"]
    if thumb and thumb.exists():
        try:  # custom thumbnails need a verified channel; harmless otherwise
            with open(thumb, "rb") as f:
                httpx.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
                           content=f.read(), timeout=60,
                           headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"})
        except Exception:  # noqa: BLE001
            pass
    if made_for_kids:
        _ensure_made_for_kids(vid, refresh_token)
    link = f"https://youtube.com/shorts/{vid}" if short else f"https://youtu.be/{vid}"
    return {"id": vid, "url": link, "privacy": privacy}


def _ensure_made_for_kids(video_id: str, refresh_token: str = "") -> None:
    """Read the flag back after upload and set it again if YouTube didn't keep it: all 23 early Shorts came out
    'Not made for kids' although the upload said made for kids (a COPPA risk for toddler videos)."""
    try:
        r = httpx.get("https://www.googleapis.com/youtube/v3/videos", timeout=30, params={"part": "status", "id": video_id},
                      headers={"Authorization": f"Bearer {_access_token(refresh_token)}"})
        items = r.json().get("items") or [] if r.status_code == 200 else []
        if items and items[0]["status"].get("selfDeclaredMadeForKids") is not True:
            update_video(video_id, refresh_token, made_for_kids=True)
    except Exception as e:  # noqa: BLE001
        print(f"[youtube] could not confirm made-for-kids on {video_id}: {e}")


def enforce_made_for_kids(refresh_token: str = "") -> list[str]:
    """Every video on the channel must stay 'made for kids' (COPPA: they're all for toddlers). Uploads ask for it and
    read it back, yet on Nov 23 all 25 Shorts showed 'not made for kids' again, so the worker re-checks the whole
    channel and switches back any that lost it. Returns the ids it fixed. Quota: ~2 units a check + 50 per fix."""
    h = {"Authorization": f"Bearer {_access_token(refresh_token)}"}
    ch = httpx.get("https://www.googleapis.com/youtube/v3/channels", timeout=30, headers=h,
                   params={"part": "contentDetails", "mine": "true"})
    ch.raise_for_status()
    uploads = ch.json()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while True:
        r = httpx.get("https://www.googleapis.com/youtube/v3/playlistItems", timeout=30, headers=h,
                      params={"part": "contentDetails", "playlistId": uploads, "maxResults": 50, **({"pageToken": page} if page else {})})
        r.raise_for_status()
        j = r.json()
        ids += [i["contentDetails"]["videoId"] for i in j.get("items", [])]
        page = j.get("nextPageToken")
        if not page:
            break
    fixed = []
    for i in range(0, len(ids), 50):
        r = httpx.get("https://www.googleapis.com/youtube/v3/videos", timeout=30, headers=h,
                      params={"part": "status", "id": ",".join(ids[i:i + 50])})
        r.raise_for_status()
        for v in r.json().get("items", []):
            if v["status"].get("selfDeclaredMadeForKids") is not True:
                update_video(v["id"], refresh_token, made_for_kids=True)
                fixed.append(v["id"])
    return fixed


def delete(video_id: str, refresh_token: str = "") -> None:
    """Remove an upload (takedown requests). Needs the force-ssl scope the channel was connected with."""
    r = httpx.delete("https://www.googleapis.com/youtube/v3/videos", params={"id": video_id}, timeout=30,
                     headers={"Authorization": f"Bearer {_access_token(refresh_token)}"})
    if r.status_code not in (204, 404):  # 404: already gone
        raise RuntimeError(f"YouTube delete failed {r.status_code}: {r.text[:200]}")


def ensure_playlist(title: str, description: str = "", refresh_token: str = "") -> str:
    """The id of the channel's public playlist with this title; created if it doesn't exist yet."""
    h = {"Authorization": f"Bearer {_access_token(refresh_token)}"}
    page = None
    for _ in range(5):
        r = httpx.get("https://www.googleapis.com/youtube/v3/playlists", timeout=30, headers=h,
                      params={"part": "snippet", "mine": "true", "maxResults": 50, **({"pageToken": page} if page else {})})
        r.raise_for_status()
        d = r.json()
        for p in d.get("items", []):
            if p["snippet"]["title"].strip().lower() == title.strip().lower():
                return p["id"]
        page = d.get("nextPageToken")
        if not page:
            break
    r = httpx.post("https://www.googleapis.com/youtube/v3/playlists", timeout=30, headers=h,
                   params={"part": "snippet,status"},
                   json={"snippet": {"title": title[:150], "description": description[:4900]},
                         "status": {"privacyStatus": "public"}})
    if r.status_code >= 400:
        raise RuntimeError(f"Playlist create failed {r.status_code}: {r.text[:200]}")
    return r.json()["id"]


def add_to_playlist(playlist_id: str, video_id: str, refresh_token: str = "") -> None:
    import time
    h = {"Authorization": f"Bearer {_access_token(refresh_token)}"}
    for i in range(4):          # YouTube answers 409 "operation aborted" now and then, mostly on new playlists
        r = httpx.post("https://www.googleapis.com/youtube/v3/playlistItems", timeout=30, headers=h,
                       params={"part": "snippet"},
                       json={"snippet": {"playlistId": playlist_id,
                                         "resourceId": {"kind": "youtube#video", "videoId": video_id}}})
        if r.status_code not in (409, 500, 503):
            break
        time.sleep(2 + 3 * i)
    if r.status_code >= 400:
        raise RuntimeError(f"Playlist add failed {r.status_code}: {r.text[:200]}")

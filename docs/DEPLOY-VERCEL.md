# Deploying CartoonForge to Vercel (plan for later — today it runs on your PC)

Nothing here changes how the app runs locally. These files only take effect on Vercel:
`vercel.json`, `api/index.py`, root `requirements.txt`, `.vercelignore`, `docs/supabase.sql`.

## Why the work is split in three
Vercel functions stop after 60-300 seconds, have no ffmpeg and no lasting disk. A 12-minute episode needs
10-30 minutes of rendering. So:

| Part | Where | Cost |
|---|---|---|
| Dashboard (React) + API (FastAPI) | **Vercel** (static files + one Python function) | Hobby: free |
| Database + video storage | **Supabase** (Postgres + Storage bucket) | Free tier: 500 MB DB, 1 GB storage |
| Writing, voices, rendering, AI animation, publishing | **GitHub Actions** (`.github/workflows/worker.yml`) | Free: 2,000 min/month on private repos, unlimited on public |

```
 browser ──> Vercel: dashboard + /api ──> Supabase (episodes, characters, settings, videos)
                     │  "make episode" → dispatches the workflow           ▲
                     ▼                                                     │
              GitHub Actions runner: write → voices → render → AI clips → upload
```

## Steps (when you're ready)
1. **Supabase**: create a project → SQL editor → paste and run `docs/supabase.sql` (tables + public `episodes` bucket).
   Copy the Project URL and the `service_role` key.
2. **GitHub**: push this project to a repo. Repo → Settings → Secrets → Actions: `SUPABASE_URL`,
   `SUPABASE_SERVICE_KEY`, `SECRET_KEY` (48 random chars; the same value as on Vercel).
   Create a fine-grained token with *Actions: read & write* on that repo.
3. **Vercel**: import the repo (framework preset: Other; the settings come from `vercel.json`). Environment variables:
   ```
   ENV=production
   ADMIN_PASSWORD=<12+ chars>
   SECRET_KEY=<same as GitHub>
   CRON_SECRET=<32 random chars>
   PUBLIC_BASE_URL=https://<your-project>.vercel.app
   SUPABASE_URL=...            SUPABASE_SERVICE_KEY=...      SUPABASE_BUCKET=episodes
   WORKER_MODE=github          GITHUB_REPO=<you>/<repo>      GITHUB_TOKEN=<fine-grained token>
   ```
4. Open the site, sign in, add keys in Settings → Keys (Gemini/Groq for writing; FAL_KEY / RUNWAY_API_KEY for AI
   animation; YouTube client ID + secret). Keys are stored encrypted in Supabase, so the GitHub worker reads them too.
5. Google Cloud OAuth client: add `https://<your-project>.vercel.app/api/youtube/callback` as a redirect URI, then
   Channel → Connect.
6. Settings → Deploy shows a checklist of what is still missing.

## Scheduling
* `vercel.json` has a daily Vercel Cron for `/api/cron/tick` (publishes anything due). Hobby plans only allow daily
  crons; with 3 posts a day either upgrade to Pro and change the schedule to `*/15 * * * *`, or point a free
  scheduler (cron-job.org) at `GET https://<site>/api/cron/tick` with header `Authorization: Bearer <CRON_SECRET>`.
* The GitHub worker also runs every 6 hours (writes, renders and publishes what is due).

## Limits to know
* Request bodies on Vercel are capped at 4.5 MB (uploads go straight to Supabase with signed URLs).
* Character portraits and style previews are drawn on Vercel (Pillow), cached for 5 min / 1 h.
* Supabase free storage is 1 GB: about 8-10 rendered episodes at 1080p. `keep_days` (Settings) deletes old files;
  published episodes live on YouTube anyway.
* Full AI animation on the GitHub runner can take a long time (hundreds of clips). The workflow allows 180 min;
  hero mode fits easily.

## Local stays the same
```
cd frontend && npm run build
cd ../backend && ../.venv/bin/python -m uvicorn app.main:app --port 8000
```
SQLite + local disk + the in-process worker, exactly as before.

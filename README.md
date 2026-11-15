# CartoonForge — the "Hoppy & Friends" kids channel on autopilot ([@HoppyAndFriends](https://www.youtube.com/@HoppyAndFriends))

The Reelsmith idea, rebuilt for children: an AI studio that plans, writes, voices, animates and publishes
**10–15 minute educational kids' episodes to YouTube**. Every rule a child-development expert would apply is
written into code. Growth tools are built in: Shorts from every episode, weekly compilations, search-friendly
titles, series playlists, translations and dubbed editions.

📒 **Every step, change and fix is logged in [`docs/BUILD-LOG.md`](docs/BUILD-LOG.md).** Which AI to use for video,
the 3-videos-a-day plan and the research sources are in [`docs/AI-VIDEO.md`](docs/AI-VIDEO.md).
🎭 **Step 16:** story cast library (main / recurring / cameo), redrawn characters, art style per episode, AI hero shots or full AI animation, a redesigned dashboard, and a Vercel plan: see [`docs/API-V2.md`](docs/API-V2.md) and [`docs/DEPLOY-VERCEL.md`](docs/DEPLOY-VERCEL.md).
📈 New episodes follow what children are into right now: the **Trends** page and a daily scan of YouTube searches,
hot kids videos, Wikipedia interest and world days.

```
 planner ── world calendar (festivals, awareness days) · balanced category mix · analytics weights · no repeats
    │
 writer ─── outline → each segment written separately (long-form) · cast bible · child-psychology brief
    │  ⇅ critic ── measurable checks (sentence length, questions, pauses, repetition, song, movement, rituals,
    │              effort praise, feelings, reading grade) + a second model's rubric; weak segments rewritten
 safety ─── code gate: violence/fear/danger-to-copy/personal data/comment requests/brands/ads → blocked
    │
 voices ─── Kokoro (free, local) per character · pitch per character · answer pauses · songs on the beat grid
 music ──── original synthesized theme jingle (same every episode), sing-along backing tracks, beds, gentle SFX
 render ─── characters/icons/sets drawn in code · lip-sync · counting cards pop on the spoken number ·
    │       karaoke words · iris transitions · end card · 1920×1080 @ 24 fps, parallel workers · flash check
 QA ─────── length, flash safety, voice engine, resolution, gate, psychology score
 review ─── dashboard: watch, read script + scorecard, edit metadata, approve (or autopilot)
 publish ── YouTube (made-for-kids) · chapters · 12 translated titles · playlist · Short · weekly compilation
    │
 optimizer  bandit over pace / length / thumbnail / title styles, rewarded by avg view % × views per day;
            retention curves → which segment kinds hold or lose kids → guidance for the next scripts
```

### Pace (Settings → pace): calm · lively · rapid · auto
`rapid` (the default) changes the shot every 1.4–2.8 s, with face close-ups, reaction shots and card close-ups,
push-ins and pans inside each shot, punch-ins on the beat during songs, bouncier motion, +32% colour saturation
and faster, drum-heavier music. `auto` lets the optimizer pick from retention data. The flash-safety check
(≤3 big flashes/s) applies at every pace. The research trade-off of very fast pacing for under-5s is shown on
the Psychology page.

### Books → animated episodes (📚 Books page)
Search Project Gutenberg (public domain): Aesop, Grimm, Andersen, Kipling, Beatrix Potter, Japanese/Indian/African
folk tales and more. Collections are split into single stories. The writer adapts one story for the age band,
softens anything frightening, and casts our friends in the roles ("Bo as the Lion"), with storybook page-turn
transitions and quoted book-page cards. The description credits the book automatically. Gutendex is used for
search, with gutenberg.org's own catalogue as a fallback.

## Run locally
```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-render.txt
cd frontend && npm install && npm run build && cd ..
cd backend && ../.venv/bin/uvicorn app.main:app --reload     # prints a generated password
../.venv/bin/python -m pytest -q                            # 21 tests incl. a real render (checks size + stereo)
```
Open http://localhost:8000 and sign in. Without an AI key the studio makes a demo counting episode from a
built-in template, so you can try the whole pipeline. For episodes on any topic, add a free **Gemini** or
**Groq** key in Settings → Keys.
Connect YouTube: create an OAuth client in Google Cloud (YouTube Data API v3 + YouTube Analytics API, redirect URI
`<PUBLIC_BASE_URL>/api/youtube/callback`), paste the ID and secret into Keys, then press Channel → Connect.

## Deploy
* **One server (simplest):** `docker build -t cartoonforge . && docker run -p 8000:8000 -v cartoonforge:/data --env-file .env cartoonforge`.
  Measured: 16 cores render 1080p at ~2x real time; a 4-core box needs roughly 20–30 minutes per 12-minute episode (`render_scale: 0.667` = 720p, ~2x faster).
* **Free render farm:** set Supabase (shared database and storage), `WORKER_MODE=github`, `GITHUB_REPO`, `GITHUB_TOKEN`.
  `.github/workflows/worker.yml` renders on GitHub's runners every 6 hours and whenever the dashboard asks.
  `render.yaml` describes a Render deployment.

## Where things live
| Path | What |
|---|---|
| `backend/app/kids/psychology.py` | Age bands (pace, sentence length, shot length, answer pause…), 17 principles with their evidence, the "never" list, script analysis |
| `backend/app/kids/cast.py` | Sunny ☀️ (host), Pip 🐧 (the learner), Mimi 🐰 (songs), Bo 🦕 (big feelings), Zuzu 🦊 (world), Nana Owl 🦉 (stories) |
| `backend/app/kids/categories.py` | 15 categories (numbers, ABC, colours, animals, fables, bedtime, science, space, dinosaurs, vehicles, habits, feelings, world, music, puzzles) with segment blueprints |
| `backend/app/kids/writer.py` · `critic.py` · `safety.py` · `meta.py` · `planner.py` · `growth.py` · `languages.py` | The agents |
| `backend/app/render/` | `characters.py`, `icons.py` (60 objects), `sets.py` (23 worlds), `music.py`, `audio.py`, `frame.py`, `episode.py` |
| `backend/app/pipeline.py` | Supervisor: states, retries, scheduling, publishing, Shorts, compilations, editions, analytics |
| `frontend/` | React dashboard: Studio, Episodes, Episode detail (player, script, scorecard, safety, metadata, QA), Cast, Psychology, Calendar, Analytics, Growth, Channel, Settings, Activity |

## Made for kids (COPPA)
Every upload is declared made-for-kids, and that switch is locked on. On made-for-kids videos YouTube turns off
comments, the notification bell, cards/end screens and personalised ads. So the show never asks for comments or
personal information. Subscribe still works, so each episode asks grown-ups once, gently (`growth_cta`, can be
switched off). Asking kids for comments, brands and "buy this" are blocked by the safety gate.

### Picture & sound quality (round 3)
* **Story characters, designed per episode.** The Writer designs every character a story needs (kind, species,
  colours, outfit, hair, skin tone, age). `render/designer.py` draws them in the house style: 45+ animal presets,
  people with diverse skin tones and hair, kings, wizards and grannies. Each gets its own voice and pitch
  (`cast.guest_profile`): big animals sound deep, small ones high, children young.
* **Any book.** Fairy tales, myths and epics (Ramayana & Mahabharata, Odyssey, Norse, Maori, Arabian Nights,
  Shakespeare) and classic novels (Alice, Pinocchio, Don Quixote, Gulliver, Jules Verne…). Search covers the whole
  Gutenberg catalogue; grown-up books are adapted chapter by chapter, keeping the child-sized heart of each part.
* **Picture:** the world is rendered at 1.5× and scaled down (sharp close-ups), soft 3D shading on every character,
  lens blur behind close-ups, a warm colour grade, sunlight glow and depth haze, a gentle vignette, and x264
  `-tune animation` at CRF 18. Render workers size themselves to free memory (`RENDER_WORKERS=0`).
* **Sound:** stereo music (electric piano, marimba, glockenspiel, chorused pads, plucked bass, brushed drums)
  through a convolution reverb; the voice is cleaned up with EQ, de-essing, compression and a touch of room; a
  soft limiter; loudness normalised (measured −16 LUFS integrated, −2 dBFS peak).

### Art styles (Settings → Art style, `render/styles.py`)
Classic cartoon · Paper cutout · Comic art · Pixel art · Retro anime · PS2 style · Risograph. Each look restyles the
characters and sets once (cached) plus a light per-frame pass; paper cutout animates on twos like a real stop-motion
film. `auto` (default) lets the optimizer test looks on real viewers and keep the ones that hold children best, but
only looks that suit the episode's age band: classic and paper for every age, comic from 3, pixel/anime for 6–12s,
and PS2/risograph (mostly grown-up nostalgia) for big kids only.

## License

Code: [MIT](LICENSE). Fonts in `backend/assets/fonts` keep their own SIL Open Font License.

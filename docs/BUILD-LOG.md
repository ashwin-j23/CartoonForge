# CartoonForge — complete build log (step by step)

Everything that was asked, decided, built, changed, tested and fixed, in order. Session date: **6 November 2026**.
Project folder: `CartoonForge` (first created as `kides reelsmith`, renamed in Step 13).
Companion projects used as references: `reelsmith-v2` (Shorts studio) and `muse-studio` (virtual creators).

---

## Step 1 — The request
> "Create a kids channel, the same concept as these two projects, but only YouTube, 10-15 minute videos, attract all
> categories of children, use psychology to impress and attract children from the whole world — build it fully."

**What was done**
1. Read both existing projects to reuse what works: Reelsmith 2's LLM router (8 providers, failover), Kokoro/Edge
   voices with word timings, Supabase/SQLite data layer, encrypted keys, YouTube publisher, GitHub Actions render
   farm; Muse Studio's consistent-character and code-level-gate ideas.
2. Created a Python venv (`.venv`) and installed FastAPI, Pillow, numpy, httpx, kokoro-onnx, edge-tts, etc.
3. Downloaded the free **Fredoka** rounded font (SIL OFL licence) for kid-friendly text.

**Files created**
* `backend/app/config.py` — env config (1920×1080, 24 fps, render workers, secrets list)
* `backend/app/settings.py` — dashboard-editable settings with kid defaults, encrypted key storage
* `backend/app/db.py` — copied from Reelsmith; tables `episodes, events, settings, topics`
* `backend/app/llm/router.py`, `backend/app/tts.py`, `backend/app/storage.py` — copied from Reelsmith
* `tts.py` changes: 5 kids delivery moods (playful, story, bedtime, teacher, excited) + 50 world voices

## Step 2 — The child-psychology engine
* `backend/app/kids/psychology.py`: 4 age bands (toddler 1-3, preschool 3-5, early 5-8, big 8-12) with speech
  speed, max sentence length, minimum shot length, attention-segment length, answer pause, interactions per minute,
  repetition targets; **17 principles** with their evidence (rituals, ask-then-wait, repeat with a twist, calm pace,
  wonder questions, familiar characters, peer learner, movement breaks, songs, dual coding, praise effort, name
  feelings, silly surprises, mirrors & windows, safe colours, sing-song voice, calm ending); a "never do" list;
  script analysis (reading grade, interactions, repetition, rituals, effort praise, feelings).
* `kids/cast.py`: original cast — Sunny ☀️ (host), Pip 🐧 (learner), Mimi 🐰 (songs), Bo 🦕 (big feelings),
  Zuzu 🦊 (world explorer), Nana Owl 🦉 (stories), each with look, personality, catchphrase, fixed voice.
* `kids/languages.py`: 21 languages with native voices (localised titles + full dubbed editions).
* `kids/categories.py`: 15 categories (numbers, ABC, colours & shapes, animals, stories, bedtime, science, space,
  dinosaurs, vehicles, habits, feelings, world, music & movement, puzzles), each with a segment blueprint.
* `kids/safety.py`: code safety gate (violence, fear, unsafe words, adult, dangerous imitation, personal data,
  comment requests, commercial pressure, brands/IP) + clickbait-title checks.

## Step 3 — Writer, critic, metadata, planner
* `kids/writer.py`: outline → each segment written separately (long-form), cards spec, offline template writer.
* `kids/critic.py`: score = average of measurable checks and a second model's 7-point rubric; rewrites weak segments.
* `kids/meta.py`: parent-friendly titles, chapters from the real timeline, 12 translated titles/descriptions,
  dubbed-script translation.
* `kids/planner.py`: world calendar (23 days), balanced weighted mix, learns from analytics, never repeats topics.

## Step 4 — Everything drawn in code (no stock art, no licences)
* `render/common.py` helpers; `render/icons.py` **60 objects**; `render/characters.py` the cast (big eyes, round
  shapes, 9 emotions, 5 arm poses, mouth/blink variants); `render/sets.py` **23 backgrounds** with gentle living
  overlays (clouds, stars, bubbles, snow, leaves).
* Checked visually on a contact sheet; fixed clipped bunny ears, a floating penguin tuft, the banana icon, and alpha
  "holes" in cheeks.

## Step 5 — Sound and the timeline
* `render/music.py`: original synthesized theme jingle (same every episode = ritual), sing-along backing tracks on a
  beat grid, soft beds, gentle SFX.
* `render/audio.py`: voices every line per character, answer pauses with soft ticks, chimes on answers, song lines
  snapped to bars, music ducked under speech, mouth-openness per frame, counting objects pop on the spoken number.

## Step 6 — Frames, rendering, publishing, pipeline, API
* `render/frame.py`: compositor (cards, lip-sync, blinks, eyes toward the speaker, countdown ring during pauses,
  karaoke captions, chapter banners, iris transitions, intro and end card).
* `render/episode.py`: parallel frame rendering → H.264 → loudness-normalised mux; thumbnails; preview frames.
* `publish/youtube.py`: made-for-kids uploads, chunked resumable upload, playlists, stats, retention.
* `pipeline.py`: planned → writing → scripted → rendering → review → approved → publishing → published.
* `main.py`: FastAPI with password/JWT auth; `worker.py` CLI; `Dockerfile`, `render.yaml`, CI and worker workflows.
* **Fix:** Kokoro version mismatch (`sentence_pause` argument) → fallback call added in `tts.py`.
* **Verified:** 1080p episode with real Kokoro voices; flash-safety check passed; end-to-end API flow to Review.

## Step 7 — Dashboard (built in parallel by a sub-agent)
React + Vite: Studio, Episodes, Episode detail (player, script, psychology scorecard, safety, YouTube metadata, QA,
log), Cast, Psychology, Calendar, Analytics, Growth, Channel, Settings, Activity, Login. Build passed.

## Step 8 — Owner request: "subscribe must not be blocked — reach and publicity matter"
* Made-for-kids videos lose comments, the bell and end screens by law (COPPA), so **comment requests stay blocked**,
  but **subscribe/like became a warning only**, plus one parent-directed subscribe line per episode, an end card and
  a description line (`growth_cta`, `cta_line`).
* `kids/growth.py`: growth checklist; Shorts cut from every episode's song; weekly long compilations; SEO title
  phrases; series playlists.

## Step 9 — Owner request: rapid scene changes, dopamine colours, attention engineering, algorithmic reinforcement, books
* Told the owner about the research trade-off of very fast pacing for under-5s (Lillard & Peterson 2011); built it
  as a **pace setting** (calm / lively / rapid / auto), default rapid as requested. Flash safety stays fixed.
* Camera system: a new shot every 1.4-2.8 s (wide, face close-up, reaction, card close-up, two-shot), push-ins and
  pans, punch-ins on the beat; never cutting away while objects are counted or during an answer pause.
* Faster, drum-heavier music and stronger colour (`vivid`) per pace.
* `kids/optimizer.py`: Thompson-sampling bandit over pace, length, thumbnail style and title style, rewarded by
  average view % × views per day; YouTube retention curves teach which segment kinds hold or lose children.
* `kids/books.py`: Project Gutenberg books → stories → animated episodes; Gutendex search with gutenberg.org fallback.
* **Fixes:** cuts looked too similar → weighted, distinct framings; Wikimedia/Gutendex slowness handled.

## Step 10 — "Run it and open the dashboard"
* The sandbox could not expose a server to the browser, so the owner ran it with `!`. Logged in through the Chrome
  extension and checked every page.
* **Dashboard bugs found and fixed:** "Make episode" button squeezed to 46 px (a `.lg` legend style collided with
  the large-button style); page scrolling sideways; sticky sidebar broken by `overflow-x: hidden` (→ `clip`);
  Actions panel cut off at mid widths (grid `minmax(0, …)`); Books shelf never loading (16 slow searches → fixed,
  verified Gutenberg IDs).

## Step 11 — "Create an env file"
* Added a `.env` loader to `config.py` (real environment variables still win) and created `.env` (mode 600,
  gitignored) with the existing local password and secret key, a new CRON_SECRET, and empty slots for AI keys,
  YouTube OAuth, Supabase and render settings.

## Step 12 — "Video output not good — improve fully; characters from the story; all kinds of books; colour and audio"
* `render/designer.py`: draws **any story character** from a design spec (45+ animal presets, people with diverse
  skin tones, hair styles and outfits). The writer now designs each episode's characters; each gets its own voice
  and pitch (`cast.guest_profile`).
* Books shelf grew to **39 verified books**: fairy tales and fables from every continent, myths and epics (Ramayana
  & Mahabharata, Odyssey, Norse, Maori, Arabian Nights, Shakespeare), classic adventures (Alice, Pinocchio, Don
  Quixote, Gulliver, Jules Verne…). Search covers all books by default; grown-up books are adapted gently.
* Picture: soft 3D shading on every character, the world rendered at 1.5× and scaled down, lens blur behind
  close-ups, warm grade, sun glow, depth haze, vignette, x264 `-tune animation` CRF 18.
* Sound: stereo music engine (electric piano, marimba, glockenspiel, chorused pads, plucked bass, brushed drums)
  with convolution reverb; voice EQ, de-essing, compression and a small room; soft limiter.
* **Fixes:** shading too muddy → lighter; dragon wings hidden → spread wings; the sunlight glow left a visible edge;
  old men's hair looked like a helmet → bald with side tufts; wizard hat clipped.
* **Two real bugs:** out of memory with 16 workers → workers sized by free memory, smaller caches; the encoder was
  told the supersampled size instead of the output size → fixed, and a test now checks size and stereo.
* **Verified:** 1920×1080, stereo AAC, −16 LUFS, peak −2 dBFS, flash 2/s.

## Step 13 — Folder renamed to CartoonForge
* The owner ran `mv "kides reelsmith" CartoonForge`. The sandbox could not rename it itself (read-only parent).
* Gave the command to update the venv's script paths; servers started with `../.venv/bin/python -m …` work either way.

## Step 14 — Art styles
Owner asked for: pixel art, PS2 style, comic art, Lego style, claymation, paper cutout, retro anime, low-poly 3D,
risograph, miniature diorama.
* `render/styles.py`: **11 looks** (classic + the 10). Each restyles characters and sets once (cached) plus a light
  per-frame pass; stop-motion looks animate on twos. "Lego" became a generic **toy bricks** look (trademark).
* Honest guidance in code: tactile toy-like looks for 2-8s; pixel/anime for 6-12s; PS2/low-poly/risograph for big
  kids only. `art_style: auto` lets the optimizer test looks on real viewers within those limits.
* Wired into `characters.py`, `sets.py`, `frame.py`, `episode.py` (thumbnails), `optimizer.py`, `pipeline.py`,
  `settings.py`, `main.py` (`/api/styles/{style}.png` previews) and the Settings page (style picker).
* **Fixes after the visual check:** claymation too close to classic → plasticine bumps, form shadow, waxy highlight;
  anime too subtle → hard cel shadow; pixel palette turned Mimi salmon → 64-colour octree palette.

## Step 15 — Which AI for video, 3 videos a day, trend analysis (this step)
**Research** (sources in `docs/AI-VIDEO.md`): Veo 3.1 Lite and Kling are the cheapest video models (≈$0.03-0.10/s);
Sora's API is reported retired; Google's official quota table now lists an upload at **1 unit** with 100
uploads/day; YouTube's inauthentic-content policy demonetises mass-produced, templated channels and hits kids'
animation hardest.

**Decisions**
* Keep the code renderer for full episodes (free, consistent, exact); add **AI-illustrated backgrounds** via Gemini
  2.5 Flash Image or OpenAI gpt-image-1 (`render/aiart.py`, setting `ai_backgrounds`, off by default).
* **3 episodes a day**: `episodes_per_day: 3`, `post_times: 07:00, 12:30, 17:30`, every day; the planner keeps two
  days of episodes in the pipe; `max_posts_per_day: 3` (Shorts ride along).
* **Variety guard** (`pipeline.similarity_to_recent`): rewrites a script whose 4-word phrases overlap more than 32%
  with a recent episode — protection against the "repetitive content" policy.
* **Trend analyser** `kids/trends.py`: YouTube search autocomplete (8 countries, no key), hot kids videos of the last
  14 days ranked by views per day (needs `YOUTUBE_API_KEY`), Wikipedia pageview jumps for 43 kid subjects, upcoming
  world days → the AI merges them into ranked ideas with an original angle (brands/shows never copied); without an
  AI key a heuristic ranks the raw signals and skips holidays that just passed.
* Planner: `trend_share` (60%) of new episodes come from trends, the rest from the balanced mix; daily scan in the
  heartbeat; trend angle passed to the writer.
* API: `GET /api/trends`, `POST /api/trends/scan`, `POST /api/trends/{id}/make`. Dashboard: new **📈 Trends** page;
  Settings: episodes per day, posting times, trend share, variety guard, AI backgrounds, `YOUTUBE_API_KEY`.

**Files changed in Step 15**: `kids/trends.py` (new), `render/aiart.py` (new), `docs/AI-VIDEO.md` (new), `db.py`
(trends table), `config.py` (YOUTUBE_API_KEY), `settings.py`, `kids/planner.py`, `pipeline.py`, `render/sets.py`,
`render/frame.py`, `main.py`, `frontend/src/pages/Trends.jsx` (new), `Layout.jsx`, `main.jsx`, `Settings.jsx`,
`styles.css`.

**Fixes during Step 15**: Wikimedia blocked a vague User-Agent after the first call → descriptive UA with a contact
URL + throttling + retries (43/43 subjects now load in ~1 min).

**Verified**: live autocomplete (80 phrases), live Wikipedia (Thanksgiving ×1.64, Christmas ×1.58, Diwali ×1.37
rising); 3 slots a day generated; planner takes top trends then the mix; variety guard flags 86% overlap between
template episodes; 14 tests pass; dashboard compiles.

**Not verified yet (needs keys)**: AI trend analysis and episode writing (AI key), hot-video signal (YouTube API
key), AI backgrounds (Gemini/OpenAI key), YouTube upload/analytics (OAuth).

---

## How to run
```
cd CartoonForge/frontend && npm run build
cd ../backend && ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open http://localhost:8000. The password is printed at startup and saved in `backend/data/.dev_admin_password`.

## Where sample renders went
Test renders and contact sheets were written to the session scratchpad (temporary). They are not part of the project.

## Step 16 — Story cast library, characters redrawn, art style first, AI animation, full UI redesign, Vercel plan
Owner asked for: characters created from the stories (every character important, some are cameos), a full character
redesign, art style made more important, the AI that makes pro-level animation, a Vercel deploy plan (runs on the PC
for now), and a complete UI/UX redesign.

* **Character library** (`kids/library.py`, table `characters`): tiers main / recurring / cameo. Every story character
  the Writer designs is saved after writing (`harvest`), reused by id or name when it returns (`match`, writer
  `_from_library`), and promoted to recurring after 3 episodes. Recurring/main friends are in every writer brief.
  Saved voice + pitch are always used (`cast.guest_profile`). "Design from a story" (AI, or a keyword designer
  without a key). API: `/api/characters` CRUD, `/api/characters/from-story`, portraits in any art style
  (`/api/cast/{id}.png?style=`). Core cast: personality/catchphrase/voice editable (setting `core_overrides`).
* **Characters redrawn** (`render/characters.py`, `render/designer.py`): shared drawing kit (plum outlines, tapered
  strokes, violet form shadow + warm rim light, layered eyes per emotion, bent arms with real hands). New silhouettes
  for all 6 cast and 46 species; humans with 9 hair styles, outfits by role. 20-60 ms per 700 px sprite (was 64-94).
* **Art style per episode**: `art_style`, `animation`, `ai_budget_usd` on create; `POST /episodes/{id}/restyle`;
  `GET /api/styles`; `pipeline.style_for` (episode choice > optimizer > channel default).
* **AI animation** (`render/aivideo.py`): modes code / hero / full. Image-to-video from the exact code-rendered frame
  (characters stay on model), our soundtrack kept, budget cap, failures fall back to code animation. Providers:
  Gemini Omni Flash (`gemini-omni-1.2-flash`, GEMINI_API_KEY, ~$0.07/s — the Veo 3.1 preview in the Gemini API shut
  down 22 Oct 2026), Kling 4.0 via fal.ai (FAL_KEY, ~$0.157/s), Runway Gen-4 Turbo (RUNWAY_API_KEY, ~$0.05/s).
  `/api/aivideo`, `/api/aivideo/estimate`. Settings: animation, ai_video_provider, ai_video_budget_usd, ai_video_hero_shots.
* **UI/UX redesign** (`frontend/`): new IA (Home, Episodes, Schedule · Characters, Looks, Library · Insights, Channel
  · Settings, Activity), guided 5-step Create flow with the art-style picker as its centrepiece and a live AI-cost
  estimate, Characters page, Looks gallery, Restyle dialog, AI video panel, Deploy checklist; design tokens, real
  light/dark themes, accessible modals/drawers, responsive to 380 px. Old routes redirect.
* **Vercel (prepared, not deployed)**: `vercel.json`, `api/index.py`, root `requirements.txt` (API only),
  `.vercelignore`, `docs/supabase.sql`, `docs/DEPLOY-VERCEL.md`, `/api/deploy` checklist, cron accepts Vercel's
  `Authorization: Bearer`. Local run unchanged.

**Verified**: 21 tests pass (7 new: library harvest/promotion/reuse, attach, keyword designer, style choice, AI hero
compositing with a fake provider — clip pixels land at the right times, soundtrack kept, budget arithmetic). The API
imports without the voice/ML packages (Vercel). Headless-Chrome end-to-end: story → 4 cameo characters, Create wizard
→ episode stored with claymation + hero, no console errors, no horizontal scroll on phone.

**Not verified yet (needs keys)**: real AI video calls (Omni / Kling / Runway), AI character design (AI key), Vercel
+ Supabase deploy.

## Step 17 — Automatic, lifelike expressions
Owner asked: expressions should change automatically and realistically.
* `render/expression.py` (new): the speaker's face changes mid-line on feeling words, timed to the spoken word
  ("oh no" → worried, "wow" → surprised, "hmm" → thinking, "yay" → excited, "well done" → proud), then eases back;
  lines ending in "!" land with energy; answers light up; during a question pause the asker waits hopefully, thinks
  along, then looks excited just before the answer. Listeners (friends and Sunny) mirror the speaker a beat later
  (0.35-0.6 s, different per character; sadness → worried, empathy) and glance between happy and calm while
  listening. Calm/bedtime lines only allow gentle faces. Changes are at least 0.6 s apart and hidden by a blink.
  Wired into `render/frame.py` for speakers, listeners and Sunny.
* Characters page: portraits act on their own (short "beats" of feelings with uneven human timing, a pose per
  feeling, soft cross-fade, only cards on screen animate, reduced-motion respected). "✨ Auto" chip; picking an
  emotion holds it, Auto resumes. Same in the character drawer.
* Verified: 23 tests (2 new); frames rendered across "Oh no, it fell down! Wow, look… Yay, well done!" show Bo
  worried → surprised → excited with Pip/Mimi/Sunny reacting; headless browser shows cards cycling independently.

## Step 18 — Hoppy the frog, the main character
* New core character **Hoppy** (`kids/cast.py`, id `hoppy`, `STAR = "hoppy"`): a bright aqua tree frog (distinct
  from Bo's green) with eye domes on a wide head, crouched springy legs, round toe pads, a speckled back, a wide
  grin with dimples and an orange hero scarf; crouches lower when sad, springs up when excited. Drawn in the shared
  kit (`render/characters.py` `_frog`, ~21 ms per sprite), works in every art style. Voice: Kokoro am_puck+am_liam.
* Main character everywhere: the writer brief opens with "MAIN CHARACTER: Hoppy" (in every segment, the adventure
  is his, ~1/3 of non-narration lines, catchphrase "Hop to it, friends!" in the hello); `clean_scenes` keeps him in
  the picture when there's room; the no-AI template stars him (asks the counting questions, leads "Hop one… five!");
  the opening jingle has him hopping beside Sunny; he stands in the middle of the end card; thumbnails lead with
  him whenever he speaks. Dashboard: "⭐ Star" badge, shown first in Characters, on Home and Login.
* Verified: 23 tests pass; contact sheet of all emotions × poses × styles; intro / scene / end card / thumbnail frames.

## Step 19 — Looks trimmed to seven
Owner asked to remove Claymation, Toy bricks, Miniature diorama and Low-poly 3D.
* Removed from `render/styles.py` (entries, sprite/background/frame effects, the brick-mosaic helper; the faceted
  helper stays for PS2 backgrounds), the optimizer's style arms, AI art/video prompt words, settings comment, README.
* Remaining: Classic cartoon, Paper cutout, Comic art, Pixel art, Retro anime, PS2 style, Risograph.
* Safety: a saved channel default or episode that still names a removed look falls back (optimizer treats it as
  auto; render uses classic); the API rejects removed looks. Cached previews deleted. 24 tests pass (1 new).

## Step 20 — Research-based colour palettes
Owner asked to use the palettes from Filmora's kids colour-palette guide and The Straits Times' kids-video analysis.
* Fetched both pages. Filmora: 15 named palettes (playful, pastel, bold, educational) + advice (pastels for babies,
  toddlers and bedtime; bolder for older kids; 1-2 main + 2-3 supporting colours; a neutral for text; colour-code
  topics). Straits Times (the page blocks the fetch tool; read with curl): measured dominant OKLCH colours of real
  shows — high chroma + many hues (Paw Patrol) = most stimulating, calmer narrative shows use fewer softer hues;
  balance matters. Its three measured palettes (unlabelled by show) kept as "Real-show palette A/B/C".
* `render/palette.py`: all 18 palettes with sources; one palette per episode chosen from category + age band
  (numbers/abc → Alphabet Classroom Brights, science → Science Lab Spark, stories/books → Storybook Naptime,
  bedtime → Cotton Candy Skies, dinosaurs → Gentle Dino Friends, music → Music Room Rhythm, toddlers → Dreamy
  Nursery Pastels, big kids get the bold variants, space is Space Explorer Night only for older kids); calm
  segments switch to a pastel companion; saturation capped by age (toddler 1.0, preschool 1.14, early 1.24,
  big 1.32 — the old "rapid" boost was 1.32 for everyone). Roles: accents, sing-along highlight (sunniest colour),
  button fill (always ≥3:1 for white text), soft set wash.
* Applied to: card frames and numerals, counting numbers, sing-along word highlight, chapter banners, question
  countdown, name tags, logo letters, end-card button, thumbnail title + age badge, set colour wash.
* Per episode `palette` (create, restyle), channel default `palette` (Settings / Looks), `GET /api/palettes`,
  episodes report `rendered_palette`. Dashboard: palette gallery with hex codes and sources on Looks, palette
  picker in Create (art-style step) and Restyle, palette badge on episodes.
* Verified: 25 tests (1 new); frames for 6 category/age combinations; headless browser (19 palette cards, set
  default works, no console errors, no horizontal scroll on phone).

## Step 21 — Channel intro (entry animation)
* `render/intro.py`: 8 s 1080p intro for the CartoonForge channel (storyboard in `docs/INTRO.md`): iris open,
  Sunny rises, Hoppy hops in, friends pop up, the name bounces in, tagline, waves, iris close; theme jingle + sfx.
  `layers()` exports a layered SVG (each character, letter, tagline, sparkle a named group) for SVGator.
* Rendered `backend/data/media/intro/cartoonforge-intro.mp4` + `cartoonforge-intro-layers.svg`. Checked: 8.0 s,
  1920×1080/24 fps, stereo AAC, −18 dB mean, no flashing.
* SVGator (Free plan): exports only web SVG (video/GIF/Lottie are paid). The editor's "Edit project" switch hung on
  a loading spinner in Brave (twice, after a reload), so the SVGator version is not built yet.

## Step 22 — Bug sweep + real 3D episodes
Owner: "not complete, analyse and fix the bugs, the video isn't good or realistic, make 3D characters and video".

**Analysis (fresh render with the current code)**
* QA "Length 10-15 min" passed a 2.9-3.7 min demo episode (template scripts were allowed 1-16.5 min).
* The no-AI demo template made ~3.7 min for a 12 min target.
* Camera close-ups sliced characters and cards in half ("How ma…", half a "5").
* Fully plum frames between segments (iris held closed in the segment gap).
* "Thinking" face read as grumpy; question pauses showed everyone squinting.
* Cards covered Sunny (top right).
* onnxruntime (Kokoro TTS) tried to send telemetry to mobile.events.data.microsoft.com.
These 2D fixes are in render/frame.py, characters.py, expression.py, writer.py, pipeline.run_qa, tts.py.

**3D cartoon look (`toy3d`)** — Blender 4.5.16 LTS (official portable build, sha256-verified) in
`backend/tools/blender` (git-ignored; `BLENDER_BIN` overrides).
* `render/three_d/blender_scene.py` (runs inside Blender): 3D sets built from the same SETS specs (sky gradient,
  rolling hills, trees, houses, fences, sea, stage, classroom walls, clouds) and the cast as soft vinyl-toy figures
  (subsurface + clear-coat) with an inverted-hull cartoon outline that is camera-only (never casts shadows).
  Hoppy, Pip, Mimi, Bo, Zuzu, Nana Owl and Sunny hand-built; story characters (any species / humans with skin,
  hair, crowns, hats) from the designer spec. Faces: eyes with iris/pupil/highlight and look direction, closed-eye
  arcs (blink, proud "^ ^"), brows (arch, raise, tilt), smile/frown arc or open mouth + tongue (lip-sync), beaks
  that open. Arms per pose (wave, cheer, point, clap). Cycles with OpenImageDenoise; GPU (OptiX/CUDA) used
  automatically when Blender sees one, else CPU.
* `render/three_d/__init__.py`: per-frame states from the same Timeline (expressions, blinks, mouth curve, cast
  layout, hops/dance, the 2D camera plan turned into a 3D dolly), Blender render, then the HUD composited at
  24 fps (cards zoom with the camera; captions, banners, countdown, logo, end card), H.264 + loudnorm AAC,
  thumbnail from the best 3D frame. Quality: draft 960×540@12, standard 1280×720@12, high 1920×1080@24.
* Style `toy3d` ("3D cartoon") in styles.py — never picked by "auto" (slow); without Blender it falls back to
  classic 2D. `/api/styles/toy3d.png` renders a real 3D preview. Settings: `render_3d_quality`, `render_3d_engine`
  (+ Settings page). Tests: tests/test_3d.py (frame planning, specs, auto exclusion, a real Blender still).
* Speed on this machine's CPU (sandbox has no GPU access): ~2 s per 960×540 frame when the CPU is free.
* 2D fixes verified (helper agent): shot framing keeps every character/card fully in or fully out (scene boxes +
  `_fit_shot` + clamped drift/pan/punch); segment transitions blank ≤2 frames; friendly thinking/calm/sleepy faces;
  Sunny moves top-left in card segments; honest QA length (0.8-1.35× the episode's target, demo labelled);
  demo template reaches the target length (counting rounds, 2 song verses, movement, feelings, "Hoppy and the Lily
  Pads" story, games), length model calibrated on a real Kokoro render; onnxruntime telemetry disabled
  (ORT_DISABLE_TELEMETRY + disable_telemetry_events). Demo title now "Counting with Hoppy and Friends".
  `backend/pytest.ini` (testpaths = tests) so pytest ignores the Blender folder. 38 tests pass.

## Step 23 — Full auto mode
Owner asked for a fully automated function.
* `backend/app/automation.py`: one switch (`full_auto`; Home page card, `PUT /api/automation`) turns on planning,
  writing, rendering, auto-approval, publishing, Shorts, weekly compilations and the optimizer. Each 5-minute
  heartbeat now also **retries failed episodes** (max 2, 30 min apart, from the step that failed; never a
  safety-blocked script) and **auto-approves** Review episodes into the next posting slot — only when every gate
  passes: real AI script (never the demo), safety gate, QA, psychology score ≥ quality bar, YouTube connected,
  kill switch off, made-for-kids on. Held episodes record why (`auto_hold`), shown on the Home card.
* Fixed: without an AI key the planner kept queuing identical demo episodes (up to 7) and rendering them all;
  now it keeps one.
* Autopilot at render time uses the same gates (before: QA + score only, so a demo could be auto-approved).
* `GET /api/automation` (readiness checklist, today's counts, next slots, held episodes, last heartbeat, recent
  automated actions), `POST /api/automation/run` (one cycle now). Tests: tests/test_automation.py. 43 tests pass.

# API v2 additions (Step 16): character library, art styles per episode, AI animation

All endpoints need the Bearer token unless noted. Existing endpoints are unchanged unless listed here.

## Characters (the story cast library)
Every character in the show lives here. Tiers:
* `main` — the core cast (Sunny, Pip, Mimi, Bo, Zuzu, Nana Owl) plus anyone promoted to main. In every writer brief.
* `recurring` — story characters that come back (auto-promoted after 3 episodes, or by hand). In every writer brief.
* `cameo` — designed for one story; saved, reused automatically if the same character appears again.

Character object:
```json
{"id": "wolf", "name": "Wolf", "tier": "main|recurring|cameo", "core": false,
 "kind": "animal|human|cast", "species": "wolf", "gender": "f|m", "age": "child|adult|old",
 "colors": {"main": "#8c91a5", "accent": "#e1e4eb"}, "outfit": "scarf", "skin": null, "hair": null, "hair_color": null,
 "personality": "...", "look": "one-line visual description", "catchphrase": "",
 "voice": "kokoro:am_michael", "pitch": 1.0,
 "origin": {"type": "core|story|custom|book", "episode_id": "...", "story": "The Boy Who Cried Wolf", "book": "Aesop"},
 "appearances": 3, "episodes": ["eid", "..."], "created_at": "...", "updated_at": "...",
 "portrait_url": "/api/cast/wolf.png"}
```
* `GET /api/characters?tier=main|recurring|cameo&q=text` → list (main first, then recurring, then cameo; newest first)
* `GET /api/characters/{id}` → character + `episodes_detail: [{id,title,status}]`
* `POST /api/characters` body: any character fields (name required) → created as `custom` (tier default `recurring`)
* `PATCH /api/characters/{id}` body: any of name, tier, personality, look, catchphrase, colors, outfit, skin, hair,
  hair_color, species, gender, age, voice, pitch → updated character. Core cast: only tier is fixed to main;
  personality/catchphrase/voice editable.
* `DELETE /api/characters/{id}` → `{ok:true}` (core cast: 400)
* `POST /api/characters/from-story` body `{"title": "The Lion and the Mouse", "text": "story text (≤20k chars)", "book": "Aesop"}`
  → `{"characters": [character, ...], "created": n, "reused": n}`. Designs every character the story needs
  (AI if a key is set, otherwise a keyword designer) and saves them as `cameo` (or reuses existing ones).
* Portraits: `GET /api/cast/{id}.png?emotion=happy|excited|surprised|thinking|sad|worried|proud|sleepy|calm&arms=down|wave|up|point|clap&size=360&style=<art style id>`
  (no auth). Works for every library character. `style` renders the portrait in that art style.

## Art styles (looks)
* `GET /api/styles` → `[{"id","label","note","bands":[...],"stepped":bool,"preview_url":"/api/styles/<id>.png","best_for":"Ages 2-8", "ai_words": "prompt words used for AI art"}]`
* `GET /api/styles/{id}.png` (no auth, existing) — a sample frame.
* Episodes now carry `art_style` (a style id or `auto`) and `animation` (`code|hero|full`), both in the summary
  (`GET /api/episodes`) and full episode.
* `POST /api/episodes` accepts optional `art_style`, `animation`, `ai_budget_usd` (number).
* `POST /api/episodes/{id}/restyle` body `{"art_style": "paper", "animation": "hero"}` (either optional)
  → re-renders the episode in that look. 409 if busy, 400 if no script.

## AI animation ("pro level")
Three modes, per episode (default from Settings → `animation`):
* `code` — CartoonForge renderer only (free, exact lip-sync and counting).
* `hero` — the code render plus AI-animated hero shots (opening tease, story climaxes, song start; 4-8 clips of 5-8 s).
  ~$1-5 per episode.
* `full` — every shot is re-animated by the AI video model, image-to-video from the code frame (so characters stay
  on model). Our voices/music stay; a budget cap stops spending and keeps code shots for the rest. ~$25-300/episode.

* `GET /api/aivideo` →
```json
{"providers": [{"id":"veo","label":"Google Veo 3.1","model":"...","key":"GEMINI_API_KEY","configured":true,
                "usd_per_s":0.15,"clip_s":[4,6,8],"best_for":"...","note":"..."}, ...],
 "recommended": "veo", "active": "veo|null",
 "modes": [{"id":"code","label":"...","note":"..."},{"id":"hero",...},{"id":"full",...}],
 "estimate": {"code": 0, "hero": 3.2, "full": 120.0}   // USD for a target_minutes episode with the active provider
}
```
* `GET /api/aivideo/estimate?mode=hero&minutes=12&provider=veo` → `{"usd": 3.2, "clips": 6, "seconds": 48}`
* Episode full object gets `ai_video: {"mode","provider","clips":[{"t":12.5,"dur":8,"status":"ok|failed|skipped","usd":1.2}], "usd": 4.1}` after render.

New settings keys (GET/PUT /api/settings): `animation` ("code"), `ai_video_provider` ("auto"|"veo"|"kling"|"runway"),
`ai_video_budget_usd` (5), `ai_video_hero_shots` (6).
New keys (GET/PUT /api/keys): `FAL_KEY` (Kling via fal.ai), `RUNWAY_API_KEY`. Veo uses `GEMINI_API_KEY`.

## Deploy info
* `GET /api/deploy` → `{"target":"local|vercel|docker","db":"sqlite|supabase","worker":"inline|github","checklist":[{"title","done","detail"}]}`

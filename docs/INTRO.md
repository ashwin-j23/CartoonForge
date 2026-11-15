# CartoonForge channel intro (entry animation)

**File:** `backend/data/media/intro/cartoonforge-intro.mp4` — 8.0 s, 1920×1080, 24 fps, H.264 + AAC stereo
(also served by the dashboard at `/media/intro/cartoonforge-intro.mp4`).
**Editable layers for SVGator:** `backend/data/media/intro/cartoonforge-intro-layers.svg` (960×540, every piece a
named group: background, sunny, pip, mimi, hoppy, bo, zuzu, nana, letter_00_C … letter_11_e, tagline, sparkle_0-4).
**Re-render:** `cd backend && ../.venv/bin/python -m app.render.intro data/media/intro/cartoonforge-intro.mp4 --svg data/media/intro/cartoonforge-intro-layers.svg`
(`--name` / `--tagline` to change the text). Code: `backend/app/render/intro.py`.

| Time | Picture | Sound |
|---|---|---|
| 0.0–0.7 s | A soft plum iris opens on the sunny meadow | Theme jingle starts |
| 0.3–1.4 s | Sunny rises over the hills, smiling | Whoosh |
| 1.1–2.6 s | **Hoppy** hops in from the right — three bouncy hops with squash and stretch — and lands in the middle | Boing ×3 |
| 2.5–3.8 s | Friends pop up one by one: Pip, Mimi, Bo, Zuzu, Nana Owl | Pop ×5 (panned left→right) |
| 3.6–5.0 s | **CartoonForge** drops in letter by letter and bounces, each letter a Rainbow Playground colour | Soft pops |
| 4.9–5.7 s | Tagline pill slides up: "Songs, stories & smiles!"; sparkles drift | — |
| 5.6–7.3 s | Everyone waves; Hoppy does a happy hop; characters bob and blink | Chime |
| 7.3–8.0 s | A soft plum iris closes | Music fades out |

Kid-safe checks: no flashing (largest frame-to-frame brightness change 24/255, at most 2 per second), age-capped
saturation (preschool), loudness −18 dB mean / −1 dB peak.

Palette: Filmora "Rainbow Playground Fun" (#ff6b6b #ffd93d #6bcb77 #4d96ff #f2f2f2).

# CartoonForge — project record

Owner: OpsMonsters · Record date: 6 November 2026 · Companions: Reelsmith 2 (pipeline, LLM router, voices,
YouTube publisher reused) and Muse Studio (consistent characters, code-level gates).

> **The full step-by-step history of every request, decision, change, fix and test is in `docs/BUILD-LOG.md`.**
> AI video/image recommendations, the 3-a-day plan and sources are in `docs/AI-VIDEO.md`.

## What was asked
A kids' YouTube channel built on the same idea as Reelsmith: YouTube only, 10–15 minute videos, appealing to
every kind of child worldwide, using child psychology to attract and hold attention. Mid-build the owner asked
for growth (reach, subscribers, publicity) to be a priority.

## Decisions
* **Attention that is earned, not extracted.** Pacing, participation pauses, repetition, rituals, songs, movement,
  peer learner, baby-schema characters (psychology.py lists the evidence for each). This is also what YouTube's
  quality principles for kids' content reward in recommendations and on YouTube Kids.
* **Growth, within the rules.** Made-for-kids disables comments, the bell and end screens, so growth comes from
  search titles, Shorts, compilations, playlists, posting consistently, translations and dubbed editions. There is one parent-directed
  subscribe line per episode. Subscribe/like wording is a *warning* (shown in Review); asking for comments or
  personal data is *blocked*.
* **Everything drawn in code.** Characters, 60 icons and 23 sets, so there are no licences, no Content ID claims and no
  drift between episodes. The music is synthesized for the same reasons.
* **Animals, not people,** for a cast that every culture can relate to; inclusion comes through names, foods,
  festivals and places in the scripts.
* **Long-form writing is chunked.** An outline comes first, then each segment is written separately; the Critic sends back only weak segments.

## Status (6 Nov 2026)
Built and tested: the full pipeline, from the API through writing, the critic, the safety gate, Kokoro voices, the 1080p render, QA,
review, approval/scheduling and Short cutting (11 tests pass, including a real render). The dashboard builds. Not yet exercised against live
services: YouTube upload/playlists/analytics (needs the owner's OAuth client), AI writing (needs a key),
Supabase + GitHub render farm, dubbed editions (needs a key), and the frontend has not been clicked through.

## Round 2 (6 Nov 2026): rapid pace, optimizer, books
* Pace profiles calm/lively/rapid/auto (psychology.PACES). The owner chose rapid as the default; the research
  trade-off for under-5s is documented and shown in the dashboard. Flash safety is never relaxed.
* Camera system in render/frame.py: weighted, deliberately distinct shots (wide / face / reaction / card / two / Sunny),
  never cutting away from objects while they are being counted or from a question during its answer pause.
* kids/optimizer.py: Thompson-sampling bandit over pace, minutes, thumbnail style (face/object/duo) and title style
  (search/character/question). Reward = avg view % × log(1 + views/day). Retention curves (YouTube Analytics
  audienceWatchRatio) are mapped onto segments to rank segment kinds, and the result feeds the Writer.
* kids/books.py: public-domain books → stories → adapted episodes (roles, page cards, credit line).
* Tests: 14 pass. Live-tested: Gutenberg search/download/split (Aesop 110 stories, Grimm 66). Not live-tested:
  the optimizer against real YouTube Analytics; the new dashboard screens.

## Round 3 (6 Nov 2026): story characters, any book, picture & sound
* Character designer, guest voices, the books shelf extended to myths, epics and classics (all IDs verified on gutenberg.org).
* Supersampled world, shading, depth of field, colour grade, vignette, animation-tuned encoder.
* Stereo music engine with reverb; voice clean-up chain; soft limiter.
* Fixed: OOM with 16 workers (render workers now sized by free memory, smaller caches); the encoder was told the
  supersampled size instead of the output size (a regression test now checks the encoded size and stereo).
* Verified: a 69 s test render, 1920×1080, stereo AAC, −16 LUFS, flash max 2/s, 14 tests pass.

## Open items
* Upload a channel banner/trailer, and verify the channel so custom thumbnails work.
* Non-Latin on-screen text in dubbed editions needs a Noto font (installed in Docker/CI; the renderer still uses Fredoka).
* Script editing in the dashboard (the API accepts `PATCH script`; there is no editor yet).

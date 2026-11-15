# Which AI to use for CartoonForge videos (researched 6 Nov 2026)

## Short answer
Keep the **built-in code renderer** for the full 10-15 minute episodes. Use AI **image** models for illustrated
backgrounds (built in: Settings → *AI-illustrated backgrounds*), and an AI **video** model only for short hero
moments if you want them (the 5-8 s opening tease, Shorts hooks).

| Job | Best choice now | Why |
|---|---|---|
| Full 10-15 min episodes | CartoonForge renderer (included) | Free, unlimited, characters identical in every frame and every episode, exact lip-sync and counting, flash-safe |
| Story backgrounds | **Gemini 2.5 Flash Image** (your Gemini key) or **OpenAI gpt-image-1** | A few cents per image, 16:9, follows the art style; ~6-10 per episode |
| 5-8 s hero clips / Short hooks (optional) | **Veo 3.1 Lite** (cheapest, ≈$0.03-0.05/s) or **Kling** (≈$0.07-0.10/s); **Runway Gen-4 Turbo** (≈$0.05/s, 720p) | Best quality per dollar; reachable through one API via fal.ai |
| Avoid | Sora API | Reported retired on 24 Sep 2026 |

## Why not generate whole episodes with an AI video model?
* **Cost.** 3 episodes × 12 min a day = 2,160 s of video a day. At $0.05-0.40/s that is **$108-$860 a day**, against
  roughly **$1-3 a day** for code-rendered episodes with AI backgrounds.
* **Consistency.** Video models still redraw characters slightly differently in every clip. Young children bond
  with characters that look and sound the same every time (see the Psychology page).
* **Control.** Counting objects must appear exactly when the number is spoken, mouths must match the voice, and
  flashes must stay under 3 a second. The renderer guarantees all three; a video model does not.
* **Policy risk.** YouTube's "inauthentic content" rules (July 2025, enforced at channel level through 2026)
  demonetise mass-produced, templated videos, and kids' animation is where enforcement hits hardest. Experts are
  also pressing YouTube to restrict AI content for children. CartoonForge counters this with original scripts,
  human review (autopilot off by default), a variety guard that rewrites near-duplicate scripts, and real
  educational structure.

## 3 videos a day
* **Quota:** fine. Google's official quota table now lists `videos.insert` at **1 unit**, with a separate bucket of
  100 uploads a day (`search.list` is the same: 1 unit, 100/day). 3 episodes + 3 Shorts a day is far below that.
* **Rendering:** about 10-30 minutes per episode depending on the machine (16 cores: ~2× real time), so 3 a day
  fits on one server or on the GitHub Actions render farm.
* **Quality guard:** Settings → *Variety guard* rewrites any script whose lines overlap more than 32% with a recent
  episode. Keep **human review on** until the channel has a track record; 3 a day only helps if every episode is
  genuinely different and good.
* **Default schedule:** 07:00, 12:30 and 17:30 local time (breakfast, nap or lunch, after school), every day.

Prices are from third-party comparisons (no official price sheets were found) — check each provider's pricing
page before budgeting.

## Sources
* [Google: YouTube Data API quota costs](https://developers.google.com/youtube/v3/determine_quota_cost)
* [AI Video API Pricing 2026 — CometAPI](https://www.cometapi.com/ai-video-api-pricing/)
* [AI Video Pricing 2026: Kling $0.07/s, Veo $0.40/s — Fluxnote](https://fluxnote.io/guides/ai-video-model-pricing-comparison-2026)
* [AI Video Generators Compared 2026 — Rangy](https://rangy.ai/blog/ai-video-generators-compared-2026/)
* [8 Best AI Video Generation APIs in 2026 — Apiframe](https://apiframe.ai/blog/best-ai-video-generation-apis)
* [AI Video Generation API Pricing Comparison 2026 — Crazyrouter](https://crazyrouter.com/en/blog/ai-video-generation-api-pricing-comparison-2026)
* [YouTube Monetization Policy Changes 2026 — AIR Media-Tech](https://air.io/en/monetization/youtube-monetization-policy-changes-2026-a-complete-dated-timeline)
* [YouTube updates its policy to demonetize inauthentic, mass-produced AI content — AlternativeTo](https://alternativeto.net/news/2025/7/youtube-updates-its-policy-to-demonetize-inauthentic-mass-produced-ai-generated-content)
* [YouTube's AI slop purge and faceless creators — The Next Web](https://thenextweb.com/news/youtube-ai-slop-crackdown-faceless-creators-collateral-damage)

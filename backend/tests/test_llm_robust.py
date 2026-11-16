"""AI replies in the wild: cut off by the token limit, bare lists, empty replies - the writer keeps going."""
import json

import pytest

from app.llm import router


def test_repair_truncated_keeps_complete_items():
    cut = '{"scenes": [{"speaker": "hoppy", "text": "Look at my jar!"}, {"speaker": "pip", "text": "Is it emp'
    assert router.repair_truncated(cut) == {"scenes": [{"speaker": "hoppy", "text": "Look at my jar!"}]}
    esc = '{"scenes": [{"text": "He said \\"hi\\" [ok]"}, {"text": "cut'
    assert router.repair_truncated(esc)["scenes"][0]["text"] == 'He said "hi" [ok]'
    assert router.repair_truncated('```json\n[1, 2, 3]\n```') == [1, 2, 3]
    with pytest.raises(ValueError):
        router.repair_truncated('{"a": "never closes')


def test_complete_json_salvages_then_retries_bigger(monkeypatch):
    calls = []

    def fake_complete(system, user, json_mode=False, **kw):
        calls.append(kw)
        if len(calls) == 1:
            return '{"broken": ', "gemini"                      # nothing salvageable
        return json.dumps({"ok": True}), kw.get("prefer") or "groq"
    monkeypatch.setattr(router, "complete", fake_complete)
    data, used = router.complete_json("s", "u", max_tokens=1000, prefer="gemini")
    assert data == {"ok": True} and calls[1]["max_tokens"] == 1800 and calls[1]["prefer"] == "gemini"


def test_empty_reply_moves_to_next_model(monkeypatch):
    p = router.PROVIDERS["groq"]
    monkeypatch.setattr(router, "secret", lambda k: "x" if k == p.key_env else "")
    monkeypatch.setattr(router, "_budget_check", lambda: None)
    router._cooldown.clear()
    seen = []

    def fake_call(prov, system, user, temperature, max_tokens, json_mode, model=None):
        seen.append(model)
        return "" if len(seen) == 1 else '{"ok": 1}'
    monkeypatch.setattr(router, "_call", fake_call)
    text, used = router.complete("s", "u", only=("groq",))
    assert used == "groq" and text == '{"ok": 1}' and len(seen) == 2 and seen[0] != seen[1]


def test_writer_accepts_bare_lists(monkeypatch):
    from app.kids import writer
    segs = [{"kind": "hello", "title": f"Part {i}", "set": "meadow", "minutes": 1, "beats": ["x"]} for i in range(6)]
    monkeypatch.setattr(writer, "complete_json", lambda *a, **k: (segs, "gemini"))
    plan = writer.outline(writer.categories.get("science"), "Sky", "preschool", 8, "en", None, "")
    assert len(plan["segments"]) == 6


def test_extract_json_never_returns_a_nested_fragment():
    cut = '{"title_idea": "Moon", "key_words": ["moon", "night", "sky", "glow"], "segments": [{"kind": "hello", "be'
    with pytest.raises(router.LLMError):
        router.extract_json(cut)                                   # used to return the key_words list
    assert router.extract_json('Sure! {"a": [1, 2]} hope this helps') == {"a": [1, 2]}
    assert router.extract_json('[{"x": 1}, {"x": 2},]') == [{"x": 1}, {"x": 2}]


def test_outline_is_never_salvaged(monkeypatch):
    calls = []

    def fake_complete(system, user, json_mode=False, **kw):
        calls.append(kw)
        return ('{"segments": [{"kind": "hello"}, {"kind": "le' if len(calls) == 1 else '{"segments": []}'), "gemini"
    monkeypatch.setattr(router, "complete", fake_complete)
    data, _ = router.complete_json("s", "u", salvage=False, max_tokens=6000)
    assert data == {"segments": []} and len(calls) == 2 and calls[1]["max_tokens"] == 10800


def test_short_script_gets_topped_up(monkeypatch):
    """The real Morning Routine shape: movement/feelings written far under their plan get CONTINUED (appended)."""
    from app.kids import writer
    line = {"speaker": "hoppy", "text": "one two three four five six", "kind": "say"}
    seg = lambda kind, n: {"kind": kind, "title": kind, "set": "meadow", "scenes": [dict(line)] * n}   # noqa: E731
    segments = [seg("hello", 6), seg("learn", 40), seg("movement", 3), seg("feelings", 4), seg("goodbye", 4)]
    plan = {"segments": [{"kind": "hello", "minutes": .6}, {"kind": "learn", "minutes": 2},
                         {"kind": "movement", "minutes": 1.8}, {"kind": "feelings", "minutes": 1.8},
                         {"kind": "goodbye", "minutes": .5}]}
    asked = []

    def fake_write(s, plan, cat, band, prev, lang, **k):
        asked.append((s["kind"], len(prev)))
        return [dict(line)] * 25
    monkeypatch.setattr(writer, "write_segment", fake_write)
    before = writer.template_seconds(segments, "preschool")
    writer._top_up(segments, plan, {}, "preschool", "en", 8, None, log=lambda m: None)
    kinds = [k for k, _ in asked]
    assert kinds[0] in ("movement", "feelings") and "hello" not in kinds and "goodbye" not in kinds
    assert asked[0][1] > 0                                    # it sees the lines so far: continue, don't restart
    assert writer.template_seconds(segments, "preschool") > before
    assert len(segments[0]["scenes"]) == 6 and len(segments[4]["scenes"]) == 4


def test_word_budget_uses_real_voice_speed():
    from app.kids import writer
    assert writer.WRITE_WPM >= 160                     # the band wpm (~110) made every episode ~55% too short


def test_overnight_failure_is_busy_not_failed():
    """The exact 23:29 mix: Gemini + Groq rate-limited, NVIDIA timed out, OpenAI 429 'no credits', Anthropic billing."""
    errs = ["gemini: cooling down after: 429 rate limit on every model (gemini-3.5-flash-lite): 503",
            "groq: 429 rate limit on every model (openai/gpt-oss-20b): 429 Rate limit reached",
            "nvidia: The read operation timed out",
            "openai: 429 rate limit on every model (gpt-4o-mini): 429 { 'message': 'You have no credits r",
            "anthropic: [key/billing] 400 Your credit balance is too low"]
    usable = [e for e in errs if "[key/billing]" not in e and not router._broken(e)]
    assert [e.split(":")[0] for e in usable] == ["gemini", "groq", "nvidia"]
    assert all(router._busy(e) for e in usable)
    assert router._broken(errs[3]) and not router._busy(errs[3])
    assert not router._broken("gemini: 429 You exceeded your current quota")      # free-tier minute limit = busy

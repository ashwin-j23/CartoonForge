"""Core behaviour: psychology checks, safety gate, template episode, cards, render, API."""
from pathlib import Path

from app.kids import categories, critic, psychology, safety, writer
from app.kids.meta import chapters
from app.render import icons


def _script():
    return writer.template_script("numbers", "Counting fruit to ten", "preschool", 12, seed=3)


def test_template_has_rituals_song_movement_and_questions():
    s = _script()
    kinds = [g["kind"] for g in s["segments"]]
    assert kinds[0] == "hello" and kinds[-1] == "goodbye"
    assert "song" in kinds and "movement" in kinds
    m = psychology.analyze(s, "preschool")
    assert m["questions"] >= 3 and m["effort_praise"] and m["feelings"] > 0
    assert not any("ritual" in i or "song" in i for i in m["issues"])


def test_analyze_flags_long_sentences_and_fixed_praise():
    s = _script()
    s["segments"][1]["scenes"].append({"speaker": "pip", "kind": "line", "text": "You're so smart! " + " ".join(["word"] * 30) + "."})
    issues = " ".join(psychology.analyze(s, "toddler")["issues"])
    assert "too long" in issues and "fixed-ability" in issues


def test_safety_blocks_danger_and_comment_requests_but_only_warns_on_subscribe():
    assert any(i["level"] == "block" for i in safety.check_text("Let's play with matches!"))
    assert any(i["level"] == "block" for i in safety.check_text("Tell us in the comments what you liked"))
    assert any(i["level"] == "block" for i in safety.check_text("Ask your parents to buy the new toy"))
    sub = safety.check_text("Grown-ups, tap subscribe so we can play again soon!")
    assert sub and all(i["level"] == "warn" for i in sub)
    assert not safety.check_text("Which shape matches? The lighter blue one! The swallow flies home.")
    assert not safety.check_text("At the market Mama buys mangoes.")
    gate = safety.check_episode({"script": _script(), "meta": {"title": "Counting Song for Toddlers"}})
    assert gate["ok"]


def test_clickbait_title_warns():
    assert safety.check_title("SHOCKING!!! You won't believe this")


def test_critic_routes_issues_to_segments():
    s = _script()
    m = {"issues": ["Too few interactions: 3 in ~12 min", "No effort praise ('You kept trying!')"]}
    notes = critic.notes_from_metrics(s, m)
    assert notes and all(isinstance(k, int) for k in notes)


def test_every_category_is_complete():
    for c in categories.CATEGORIES:
        assert c["blueprint"][0] == "hello" and c["blueprint"][-1] == "goodbye"
        assert c["topics"] and c["bands"] and c["yt"] in ("1", "10", "27")


def test_icons_resolve_plurals_and_fallback():
    assert icons.resolve("Apples") == "apple"
    assert icons.resolve("aeroplane") == "plane"
    assert icons.icon("unknown-thing", 64).size == (64, 64)


def test_chapters_start_at_zero():
    tl = [{"title": "Hello!", "start": 4}, {"title": "Count", "start": 40}, {"title": "Song", "start": 120},
          {"title": "Bye", "start": 600}]
    ch = chapters(tl).splitlines()
    assert ch[0].startswith("0:00") and len(ch) == 4


def test_preview_frame_renders():
    from app.render.episode import preview
    im = preview(_script(), {"channel_name": "Test"}, 40.0, scale=0.25)
    assert im.size == (480, 270)


def test_full_render_short_episode(tmp_path: Path):
    from app.render.episode import render
    s = writer.template_script("colors_shapes", "Rainbow colours", "toddler", 5, seed=1)
    s["segments"] = s["segments"][:2] + s["segments"][-1:]
    out = render(s, {"channel_name": "Test", "render_scale": 0.25}, tmp_path)
    assert out["video"].exists() and out["video"].stat().st_size > 10_000
    assert out["flash"]["max_per_s"] <= 3
    import subprocess
    from app import config
    info = subprocess.run([config.FFMPEG, "-i", str(out["video"])], capture_output=True, text=True).stderr
    assert f"{out['W']}x{out['H']}" in info, "encoded size must match the requested output size"
    assert "stereo" in info


def test_api_login_and_protected_routes():
    from fastapi.testclient import TestClient
    from app import config
    from app.main import app
    c = TestClient(app)
    assert c.get("/api/overview").status_code == 401
    assert c.post("/api/login", json={"password": "nope"}).status_code == 401
    tok = c.post("/api/login", json={"password": config.ADMIN_PASSWORD}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    for path in ("overview", "categories", "psychology", "growth", "calendar", "analytics", "settings"):
        assert c.get(f"/api/{path}", headers=h).status_code == 200, path
    assert c.get("/api/cast/mimi.png").status_code == 200
    s = c.put("/api/settings", headers=h, json={"made_for_kids": False, "target_minutes": 40}).json()
    assert s["made_for_kids"] is True and s["target_minutes"] == 15


def test_books_split_and_strip():
    from app.kids import books
    raw = ("Header stuff\n*** START OF THE PROJECT GUTENBERG EBOOK FABLES ***\n\nCONTENTS\n\nThe Lion\n\n\n"
           "THE LION AND THE MOUSE\n\n" + "A lion slept and a little mouse ran over his nose. " * 20 +
           "\n\nTHE TORTOISE AND THE HARE\n\n" + "The hare laughed at the slow tortoise. " * 30 +
           "\n*** END OF THE PROJECT GUTENBERG EBOOK FABLES ***\nlicence text")
    body = books.strip_gutenberg(raw)
    assert "Header" not in body and "licence" not in body
    st = books.stories(body)
    assert [s["title"] for s in st] == ["The Lion And The Mouse", "The Tortoise And The Hare"]
    assert "Gutenberg" in books.credit({"title": "X", "book": "Y", "authors": ["Aesop"], "url": "u"})


def test_optimizer_variant_and_learning():
    from app.kids import optimizer
    v = optimizer.variant()
    assert v["pace"] in ("calm", "lively", "rapid") and v["thumb"] in optimizer.ARMS["thumb"]
    curve = [(i / 10, 1 - i / 20) for i in range(11)]
    ep = {"youtube": {"id": "x"}, "duration": 600, "timeline": [
        {"kind": "hello", "start": 0, "end": 60}, {"kind": "song", "start": 60, "end": 300}, {"kind": "recap", "start": 300, "end": 600}]}
    perf = optimizer.learn_segments({"x": curve}, [ep])
    assert set(perf) == {"hello", "song", "recap"}


def test_rapid_pace_cuts_between_distinct_shots():
    from app.render.episode import estimate_audio
    from app.render.frame import Timeline, _shots
    s = _script()
    snd = estimate_audio(s, 24)
    tl = Timeline(s, snd, 480, 270, 24, {"pace": "rapid"})
    long_scene = max(range(len(snd["scenes"])), key=lambda i: snd["scenes"][i]["end"] - snd["scenes"][i]["start"])
    sc = snd["scenes"][long_scene]
    data = tl.scene_data(sc)
    on = [c for c in data["cast"] if c != "sunny"][:3]
    xs = {1: [.5], 2: [.36, .64], 3: [.27, .5, .73]}[len(on)]
    shots = _shots(tl, long_scene, sc, data, on, xs, None, data["speaker"], 480, 270)
    if sc["end"] - sc["start"] > 3.5:
        assert len(shots) >= 2
    assert all(b[0] - a[0] <= 2.81 for a, b in zip(shots, shots[1:]))
    calm = Timeline(s, snd, 480, 270, 24, {"pace": "calm"})
    assert len(_shots(calm, long_scene, sc, data, on, xs, None, data["speaker"], 480, 270)) == 1

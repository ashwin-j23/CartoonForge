"""The channel jingle: a sing-along hook on the channel name, same notes every time, works without TTS."""
import numpy as np

from app.render import music


def test_hook_words_follow_the_channel_name():
    assert music._hook_words("Hoppy Hop Hop") == ["Hoppy", "Hop", "Hop!"]
    assert music._hook_words("") == ["Hello!"]


def test_jingle_shape_and_determinism():
    a = music.theme("Hoppy Hop Hop", voices=False)
    b = music.theme("Hoppy Hop Hop", voices=False)
    assert a.ndim == 2 and a.shape[1] == 2 and np.allclose(a, b)
    assert 6.5 < len(a) / music.SR < 8 and 0.5 < float(np.max(np.abs(a))) <= 0.9
    slow = music.theme("Hoppy Hop Hop", slow=True, voices=False)
    assert len(slow) > len(a)


def test_jingle_survives_without_any_voice_engine(monkeypatch):
    music._word_cache.clear()
    monkeypatch.setattr(music, "_sung", lambda *a, **k: None)
    out = music.theme("Hoppy Hop Hop")
    assert np.isfinite(out).all() and float(np.max(np.abs(out))) > 0.5

"""Brand kit: logo letters (cached, spaces kept), YouTube sizes, transparent watermark corners."""
from PIL import Image

from app.render import branding


def test_brand_letters_cached_and_spaces():
    a = branding.brand_letters("Hoppy Hop Hop", 60)
    assert a is branding.brand_letters("Hoppy Hop Hop", 60)          # cached: drawn on every frame
    assert len(a) == 13 and a[5] is None and all(im.mode == "RGBA" for im in a if im)


def test_kit_sizes(tmp_path):
    b = Image.open(branding.banner(tmp_path / "b.png"))
    assert b.size == (2560, 1440)
    av = branding.avatar(tmp_path / "a.png")
    assert Image.open(av).size == (800, 800)
    w = Image.open(branding.watermark(av, tmp_path / "w.png"))
    assert w.size == (150, 150) and w.mode == "RGBA" and w.getpixel((0, 0))[3] == 0

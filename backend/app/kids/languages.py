"""Languages for a worldwide audience.

Two levels:
  * localizations — every upload carries its title + description translated into these languages, so YouTube
    shows it in the viewer's own language (cheap: one model call per episode).
  * editions — the episode dubbed (dubs.py): translated script, native voices on the same picture, uploaded to the
    second, dubbed channel; the main channel stays English. Kids under 7 can't read subtitles, so a real dub is
    what actually reaches them.
"""
from __future__ import annotations

# code -> (English name, native name, female voice, male voice)
LANGS: dict[str, tuple[str, str, str, str]] = {
    "en": ("English", "English", "kokoro:af_heart", "kokoro:am_puck"),
    "es": ("Spanish", "Español", "kokoro:ef_dora", "edge:es-MX-JorgeNeural"),
    "pt": ("Portuguese", "Português", "kokoro:pf_dora", "kokoro:pm_alex"),
    "hi": ("Hindi", "हिन्दी", "kokoro:hf_alpha", "kokoro:hm_omega"),
    "ar": ("Arabic", "العربية", "edge:ar-SA-ZariyahNeural", "edge:ar-SA-HamedNeural"),
    "id": ("Indonesian", "Bahasa Indonesia", "edge:id-ID-GadisNeural", "edge:id-ID-ArdiNeural"),
    "fr": ("French", "Français", "kokoro:ff_siwis", "edge:fr-FR-HenriNeural"),
    "de": ("German", "Deutsch", "edge:de-DE-KatjaNeural", "edge:de-DE-ConradNeural"),
    "ru": ("Russian", "Русский", "edge:ru-RU-SvetlanaNeural", "edge:ru-RU-DmitryNeural"),
    "ja": ("Japanese", "日本語", "kokoro:jf_alpha", "edge:ja-JP-KeitaNeural"),
    "ko": ("Korean", "한국어", "edge:ko-KR-SunHiNeural", "edge:ko-KR-InJoonNeural"),
    "zh-Hans": ("Chinese (Simplified)", "简体中文", "kokoro:zf_xiaobei", "edge:zh-CN-YunxiNeural"),
    "tr": ("Turkish", "Türkçe", "edge:tr-TR-EmelNeural", "edge:tr-TR-AhmetNeural"),
    "bn": ("Bengali", "বাংলা", "edge:bn-IN-TanishaaNeural", "edge:bn-IN-BashkarNeural"),
    "ur": ("Urdu", "اردو", "edge:ur-PK-UzmaNeural", "edge:ur-PK-AsadNeural"),
    "vi": ("Vietnamese", "Tiếng Việt", "edge:vi-VN-HoaiMyNeural", "edge:vi-VN-NamMinhNeural"),
    "th": ("Thai", "ไทย", "edge:th-TH-PremwadeeNeural", "edge:th-TH-NiwatNeural"),
    "fil": ("Filipino", "Filipino", "edge:fil-PH-BlessicaNeural", "edge:fil-PH-AngeloNeural"),
    "sw": ("Swahili", "Kiswahili", "edge:sw-KE-ZuriNeural", "edge:sw-KE-RafikiNeural"),
    "it": ("Italian", "Italiano", "kokoro:if_sara", "edge:it-IT-ElsaNeural"),
    "ta": ("Tamil", "தமிழ்", "edge:ta-IN-PallaviNeural", "edge:ta-IN-ValluvarNeural"),
}

# Scripts whose words aren't separated by spaces / use non-Latin glyphs need a font with those glyphs; the
# renderer shows fewer on-screen words for them (pre-readers rely on the voice anyway).
NON_LATIN = {"hi", "ar", "ru", "ja", "ko", "zh-Hans", "bn", "ur", "th", "ta"}


def name(code: str) -> str:
    return LANGS.get(code, (code, code, "", ""))[0]


def voice_for_lang(code: str, gender: str, char_id: str = "") -> str:
    row = LANGS.get(code) or LANGS["en"]
    return row[2] if gender == "f" else row[3]


def catalog() -> list[dict]:
    return [{"code": c, "name": n, "native": nat} for c, (n, nat, _f, _m) in LANGS.items()]

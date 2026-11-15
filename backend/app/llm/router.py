"""Multi-provider LLM router with automatic failover.

Every free/cheap provider worth using exposes an OpenAI-compatible
`/chat/completions` endpoint (Gemini, Groq, NVIDIA NIM, Cerebras, OpenRouter,
Mistral, OpenAI). Anthropic is called natively. The router walks the provider
order from settings, skips providers without a key or in cooldown, and returns
the first good answer. Rate-limited providers cool down so the next video uses
a different one — this is what lets you stay entirely on free tiers.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx

from ..settings import app_settings, secret


@dataclass
class Provider:
    name: str
    label: str
    key_env: str
    base_url: str
    model: str
    kind: str = "openai"  # openai | anthropic


PROVIDERS: dict[str, Provider] = {p.name: p for p in [
    Provider("gemini", "Google Gemini", "GEMINI_API_KEY",
             "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    Provider("groq", "Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    Provider("nvidia", "NVIDIA NIM", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1",
             "nvidia/nemotron-3.5-super-vl-120b-a12b"),
    Provider("cerebras", "Cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1", "llama-3.3-70b"),
    Provider("openrouter", "OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
             "meta-llama/llama-3.3-70b-instruct:free"),
    Provider("mistral", "Mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1", "mistral-small-latest"),
    Provider("openai", "OpenAI", "OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o-mini"),
    Provider("anthropic", "Anthropic Claude", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1",
             "claude-haiku-4-5", kind="anthropic"),
]}

# Tried in order when the provider says a model is gone (404/410), since free
# providers retire models often. A *_MODEL env/key override always goes first.
MODEL_FALLBACKS: dict[str, list[str]] = {
    # 2026-11-16: checked live; each model has its own free quota, so more models = more free capacity
    "gemini": ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"],
    "groq": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"],
    "nvidia": ["nvidia/nemotron-3.5-super-vl-120b-a12b", "deepseek-ai/deepseek-v4.1-flash", "z-ai/glm-5.3-flash",
               "nvidia/llama-3.1-nemotron-ultra-253b-v1"],    # 2026-11-02: only the first answered fast on a free key
    "openrouter": ["meta-llama/llama-3.3-70b-instruct:free", "openai/gpt-oss-120b:free"],
}
# Free tiers rate-limit per model, so a 429 on one model moves on to the next instead of giving up.
_RATE_LIMIT = re.compile(r"\b429\b|quota|rate limit|resource.?exhausted|too many requests|\b503\b|high demand|overloaded",
                         re.I)
# A wrong/expired key or an empty balance: that provider is unusable until the owner fixes it (not "busy").
_BROKEN = re.compile(r"\b40[13]\b|invalid.{0,20}(api )?key|incorrect api key|authori[sz]ation failed|"
                     r"credit balance|billing|insufficient.{0,10}(funds|quota|credit)", re.I)
_MODEL_GONE = re.compile(r"\b(404|410)\b.*(model|gone|not found|does not exist|decommission|retired|no longer)", re.I | re.S)
_working_model: dict[str, str] = {}

# provider (or "provider/model") -> unix time until which we skip it
_cooldown: dict[str, float] = {}
_stats: dict[str, dict] = {}


class LLMError(RuntimeError):
    pass


class LLMBusy(LLMError):
    """Every provider is rate-limited right now: wait and retry, the work itself is fine."""


def busy_until() -> float:
    """Unix time the first configured provider comes back, 0 if one is usable now."""
    now = time.time()
    ends = [_cooldown.get(n, 0) for n, p in PROVIDERS.items() if secret(p.key_env)]
    return 0 if not ends or min(ends) <= now else min(ends)


def model_for(p: Provider) -> str:
    return secret(f"{p.name.upper()}_MODEL") or _working_model.get(p.name) or p.model


def _models_to_try(p: Provider) -> list[str]:
    out = [model_for(p)] + MODEL_FALLBACKS.get(p.name, [])
    return list(dict.fromkeys(out))


def available() -> list[dict]:
    order = app_settings().get("provider_order") or list(PROVIDERS)
    out = []
    for name in order + [n for n in PROVIDERS if n not in order]:
        p = PROVIDERS.get(name)
        if not p:
            continue
        out.append({
            "name": p.name, "label": p.label, "model": model_for(p),
            "configured": bool(secret(p.key_env)),
            "cooldown_until": _cooldown.get(p.name, 0) if _cooldown.get(p.name, 0) > time.time() else None,
            **_stats.get(p.name, {"ok": 0, "fail": 0, "last_error": None}),
        })
    return out


def _call(p: Provider, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool,
          model: str | None = None) -> str:
    key = secret(p.key_env)
    model = model or model_for(p)
    if p.kind == "anthropic":
        if isinstance(user, list):   # OpenAI-style parts -> Anthropic image blocks
            user = [{"type": "text", "text": x["text"]} if x["type"] == "text" else
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": x["image_url"]["url"].split(",", 1)[1]}} for x in user]
        r = httpx.post(f"{p.base_url}/messages", timeout=90, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "temperature": temperature,
                  "system": system, "messages": [{"role": "user", "content": user}]})
        if r.status_code >= 400:
            raise LLMError(f"{r.status_code} {r.text[:200]}")
        return "".join(b.get("text", "") for b in r.json().get("content", []))

    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # Thinking tokens count against max_tokens and cut JSON replies short.
    if model.startswith("gemini-2.5-flash") or model.startswith("qwen/qwen3"):
        body["reasoning_effort"] = "none"
    elif "gpt-oss" in model:
        body["reasoning_effort"] = "low"
        body["max_tokens"] = max_tokens + 2000
    elif "nemotron" in model or "deepseek-r1" in model:
        body["messages"][0]["content"] = "/no_think\n" + system
        body["max_tokens"] = max_tokens + 2000
    if json_mode and p.name in ("openai", "groq", "gemini", "mistral", "cerebras"):
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key}"}
    if p.name == "openrouter":
        headers.update({"HTTP-Referer": "https://github.com/reelsmith", "X-Title": "Reelsmith"})
    r = httpx.post(f"{p.base_url}/chat/completions", json=body, headers=headers, timeout=90)
    if r.status_code == 400 and ("response_format" in body or "reasoning_effort" in body):
        body.pop("response_format", None)  # some models reject json mode / reasoning_effort; retry plain
        body.pop("reasoning_effort", None)
        r = httpx.post(f"{p.base_url}/chat/completions", json=body, headers=headers, timeout=90)
    if r.status_code >= 400:
        raise LLMError(f"{r.status_code} {r.text[:200]}")
    data = r.json()
    text = data["choices"][0]["message"]["content"] or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def _budget_check() -> None:
    """Daily cap on model calls (settings.llm_daily_budget) so a loop can never burn a quota."""
    from datetime import date
    from ..db import get_db
    cap = int(app_settings().get("llm_daily_budget", 300) or 0)
    if cap <= 0:
        return
    key = f"llm_usage_{date.today().isoformat()}"
    db = get_db()
    used = int(db.get_setting(key, 0) or 0)
    if used >= cap:
        raise LLMError(f"Daily AI call budget reached ({cap}). Raise it in Settings or wait until tomorrow.")
    db.set_setting(key, used + 1)


VISION = ("gemini", "nvidia", "openai", "anthropic", "mistral")    # providers whose default model reads images


def complete(system: str, user, *, temperature: float = 0.9, max_tokens: int = 2000,
             json_mode: bool = False, prefer: str | None = None, avoid: str | None = None,
             only: tuple | None = None) -> tuple[str, str]:
    """Returns (text, provider_name). Raises LLMError if every provider fails.

    prefer: try this provider first. avoid: try it last (used so a reviewer is a
    different model from the author, the "nobody grades their own work" rule).
    """
    order = list(app_settings().get("provider_order") or PROVIDERS)
    order += [n for n in PROVIDERS if n not in order]
    if only:
        order = [n for n in order if n in only]
    if prefer in order:
        order.remove(prefer)
        order.insert(0, prefer)
    if avoid in order:
        order.remove(avoid)
        order.append(avoid)
    if any(secret(PROVIDERS[n].key_env) for n in order if n in PROVIDERS):
        _budget_check()
    errors = []
    for name in order:
        p = PROVIDERS.get(name)
        if not p or not secret(p.key_env):
            continue
        st = _stats.setdefault(name, {"ok": 0, "fail": 0, "last_error": None})
        if _cooldown.get(name, 0) > time.time():
            errors.append(f"{name}: cooling down after: {(st['last_error'] or '?')[:120]}")
            continue
        models = [m for m in _models_to_try(p) if _cooldown.get(f"{name}/{m}", 0) <= time.time()]
        try:
            text, limited = None, []
            for model in models:
                try:
                    text = _call(p, system, user, temperature, max_tokens, json_mode, model)
                    if not text.strip():                     # empty (e.g. all tokens spent thinking): next model
                        st["last_error"] = f"{model}: empty response"
                        text = None
                        continue
                    break
                except LLMError as e:
                    if _RATE_LIMIT.search(str(e)):
                        _cooldown[f"{name}/{model}"] = time.time() + 600
                        limited.append(model)
                    elif not _MODEL_GONE.search(str(e)):
                        raise
                    st["last_error"] = f"{model}: {str(e)[:150]}"
            if text is None:
                if st["last_error"] and "empty response" in st["last_error"] and not limited:
                    raise LLMError("empty response from every model")
                if limited or not models:
                    raise LLMError(f"429 rate limit on every model ({', '.join(limited) or 'all cooling down'}): "
                                   f"{(st['last_error'] or '')[:120]}")
                raise LLMError(f"every model retired ({', '.join(_models_to_try(p))}); set {name.upper()}_MODEL")
            if not text.strip():
                raise LLMError("empty response")
            _working_model[name] = model
            st["ok"] += 1
            return text, name
        except Exception as e:  # noqa: BLE001 - any failure -> next provider
            msg = str(e)
            st["fail"] += 1
            st["last_error"] = msg[:200]
            # broken key / no credit -> skip for an hour; rate limit / quota -> 10 min; other errors -> 1 min
            broken = bool(_BROKEN.search(msg)) and not _RATE_LIMIT.search(msg)
            _cooldown[name] = time.time() + (3600 if broken else 600 if _RATE_LIMIT.search(msg) else 60)
            errors.append(f"{name}: {'[key/billing] ' if broken else ''}{msg[:120]}")
    if not errors:
        raise LLMError("No AI provider configured. Add at least one API key in Settings → Keys.")
    usable = [e for e in errors if "[key/billing]" not in e and not (_BROKEN.search(e) and not _RATE_LIMIT.search(e))]
    if usable and all(_RATE_LIMIT.search(e) or "cooling down" in e for e in usable):
        raise LLMBusy("All working providers are rate-limited — " + " | ".join(errors))
    raise LLMError("All providers failed — " + " | ".join(errors))


def extract_json(text: str):
    """Pull the first JSON object/array out of a model reply (handles ```json fences, prose)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except Exception:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = t.find(open_c)
        if start == -1:
            continue
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            c = t[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == open_c:
                depth += 1
            elif c == close_c:
                depth -= 1
                if depth == 0:
                    chunk = t[start:i + 1]
                    chunk = re.sub(r",\s*([}\]])", r"\1", chunk)  # trailing commas
                    return json.loads(chunk)
    raise LLMError("Model did not return valid JSON")


def vision_json(system: str, text: str, images: list[bytes], **kw):
    """JSON answer about JPEG images (frames of a video). Falls back to text only if no vision model answers."""
    import base64
    parts = [{"type": "text", "text": text}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}
        for b in images]
    try:
        return complete_json(system, parts, only=VISION, **kw)
    except LLMError:
        return complete_json(system, text + "\n\n(The frames could not be shown; use the other details.)", **kw)


def repair_truncated(text: str):
    """Salvage a JSON reply cut off by the token limit: keep every complete item, close the brackets.
    Returns the parsed value or raises ValueError."""
    t = re.sub(r"^```(?:json)?\s*", "", text.strip())
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON")
    stack, in_str, esc, last_ok = [], False, False, None
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            stack.append("}" if c == "{" else "]")
        elif c in "}]":
            if not stack:
                break
            stack.pop()
            if not stack:
                return json.loads(t[start:i + 1])
            last_ok = (i + 1, list(stack))                   # a value just closed: a safe cut point
    if not last_ok:
        raise ValueError("nothing complete to salvage")
    cut, rest = last_ok
    return json.loads(t[start:cut] + "".join(reversed(rest)))


def complete_json(system: str, user, **kw):
    """JSON completion. A reply cut off by the token limit is salvaged; otherwise it is asked again with more room,
    then on another provider."""
    text, used = complete(system, user, json_mode=True, **kw)
    try:
        return extract_json(text), used
    except Exception:  # noqa: BLE001
        pass
    try:
        data = repair_truncated(text)
        if data:
            return data, used
    except (ValueError, json.JSONDecodeError):
        pass
    again = "\n\nReturn ONLY valid minified JSON. No prose. Keep it compact."
    user2 = user + again if isinstance(user, str) else user + [{"type": "text", "text": again}]
    kw2 = {**kw, "max_tokens": int(kw.get("max_tokens", 1500) * 1.8)}
    text, used2 = complete(system, user2, json_mode=True, **{**kw2, "prefer": used})
    try:
        return extract_json(text), used2
    except Exception:  # noqa: BLE001
        _cooldown[used2] = time.time() + 30
        _stats.setdefault(used2, {"ok": 0, "fail": 0, "last_error": None})["last_error"] = \
            f"reply was not valid JSON: {text[:100]!r}"
    text, used3 = complete(system, user2, json_mode=True, **{**kw2, "avoid": used2})
    return extract_json(text), used3

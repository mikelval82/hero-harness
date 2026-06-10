import json
import threading
import unicodedata
import urllib.parse
import urllib.request

from src.integrations.constants import PROJECT_COLORS

TELEGRAM_MAX_MSG = 4096
_msg_ctx = threading.local()


def _project_color(tag):
    if not tag:
        return ""
    project = tag.split(":")[0] if ":" in tag else tag
    idx = sum(ord(c) for c in project) % len(PROJECT_COLORS)
    return PROJECT_COLORS[idx]


def _set_msg_prefix(tag):
    if tag:
        color = _project_color(tag)
        project = tag.split(":")[0] if ":" in tag else tag
        _msg_ctx.prefix = f"{color} [{project}]\n"
    else:
        _msg_ctx.prefix = ""


PHASE_EMOJI = {
    "brainstorm": "\U0001f50d",
    "spec": "\U0001f4dd",
    "plan": "\U0001f4d0",
    "implement": "⚙️",
    "reimplement": "\U0001f527",
    "review": "\U0001f50e",
    "waiting_approval": "⏳",
    "waiting_review_decision": "⏳",
}


def _safe_chunk_boundary(text, boundary):
    if boundary >= len(text):
        return len(text)
    original = boundary
    while boundary > 0:
        ch = text[boundary]
        cat = unicodedata.category(ch)
        if cat in ('Mn', 'Mc', 'Me'):
            boundary -= 1
            continue
        if ch in ('︎', '️'):
            boundary -= 1
            continue
        if '\U0001f3fb' <= ch <= '\U0001f3ff':
            boundary -= 1
            continue
        if ch == '‍':
            boundary -= 1
            continue
        if boundary > 0 and text[boundary - 1] == '‍':
            boundary -= 1
            continue
        if '\U0001f1e6' <= ch <= '\U0001f1ff':
            count = 0
            pos = boundary - 1
            while pos >= 0 and '\U0001f1e6' <= text[pos] <= '\U0001f1ff':
                count += 1
                pos -= 1
            if count % 2 == 1:
                boundary -= 1
                continue
        break
    if boundary <= 0:
        return original
    return boundary


def get_updates(token, offset, timeout=30):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = urllib.parse.urlencode({"offset": offset, "timeout": timeout})
    try:
        with urllib.request.urlopen(f"{url}?{params}", timeout=timeout + 5) as r:
            return json.loads(r.read()).get("result", [])
    except Exception:
        return []


def send_message(token, chat_id, text, parse_mode=None):
    prefix = getattr(_msg_ctx, 'prefix', '')
    if prefix:
        text = prefix + text
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    i = 0
    while i < len(text):
        end = _safe_chunk_boundary(text, i + TELEGRAM_MAX_MSG)
        chunk = text[i:end]
        payload = {"chat_id": chat_id, "text": chunk}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        data = urllib.parse.urlencode(payload).encode("utf-8")
        try:
            urllib.request.urlopen(url, data, timeout=10)
        except Exception:
            pass
        i = end

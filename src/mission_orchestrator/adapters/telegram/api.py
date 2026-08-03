from __future__ import annotations

import json
import urllib.parse
import urllib.request


API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE = 4096


def _request(token: str, method: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(API.format(token=token, method=method), data=body)
    with urllib.request.urlopen(request, timeout=70) as response:
        return json.loads(response.read().decode("utf-8"))


def get_updates(token: str, offset: int | None, timeout: int = 60) -> list[dict]:
    data: dict[str, object] = {"timeout": timeout}
    if offset is not None:
        data["offset"] = offset
    payload = _request(token, "getUpdates", data)
    return payload.get("result", []) if payload.get("ok") else []


def send_message(token: str, chat_id: str, text: str, parse_mode: str | None = None) -> None:
    for chunk in chunk_message(text):
        data = {"chat_id": chat_id, "text": chunk}
        if parse_mode:
            data["parse_mode"] = parse_mode
        _request(token, "sendMessage", data)


def chunk_message(text: str) -> list[str]:
    if not text:
        return [""]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > MAX_MESSAGE:
        split_at = remaining.rfind("\n", 0, MAX_MESSAGE)
        if split_at <= 0:
            split_at = MAX_MESSAGE
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    chunks.append(remaining)
    return chunks


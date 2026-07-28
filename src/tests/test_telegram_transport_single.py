import io
import json
import multiprocessing
import urllib.error

import pytest

from src.integrations import telegram_api
from src.integrations.telegram_lock import (
    TelegramLock,
    TelegramOffsetStore,
    token_hash,
)


class _Response:
    def __init__(self, payload, status=200):
        self.status = status
        self._raw = json.dumps(payload).encode("utf-8")
        self.closed = False

    def read(self):
        return self._raw

    def close(self):
        self.closed = True


def _hold_lock(token, root, ready, release, result):
    lock = TelegramLock(token, root)
    result.put(lock.acquire())
    ready.set()
    release.wait(5)
    lock.release()


def _hold_lock_until_killed(token, root, ready, result):
    lock = TelegramLock(token, root)
    result.put(lock.acquire())
    ready.set()
    multiprocessing.Event().wait(60)


def test_request_validates_ok_and_returns_result(monkeypatch):
    response = _Response({"ok": True, "result": {"message_id": 7}})
    monkeypatch.setattr(telegram_api.urllib.request, "urlopen", lambda *a, **k: response)

    result = telegram_api.request("secret", "sendMessage", {"text": "hello"})

    assert result == {"message_id": 7}
    assert response.closed is True


def test_request_exposes_api_error_fields(monkeypatch):
    response = _Response({
        "ok": False,
        "error_code": 429,
        "description": "Too Many Requests",
        "parameters": {"retry_after": 3},
    })
    monkeypatch.setattr(telegram_api.urllib.request, "urlopen", lambda *a, **k: response)

    with pytest.raises(telegram_api.TelegramAPIError) as caught:
        telegram_api.request("secret", "sendMessage")

    assert caught.value.error_code == 429
    assert caught.value.retry_after == 3
    assert caught.value.retryable is True
    assert caught.value.fatal is False


def test_request_rejects_empty_response(monkeypatch):
    monkeypatch.setattr(telegram_api.urllib.request, "urlopen", lambda *a, **k: None)

    with pytest.raises(telegram_api.TelegramAPIError, match="empty response") as caught:
        telegram_api.request("secret", "sendMessage")

    assert caught.value.retryable is True


def test_request_rejects_invalid_json(monkeypatch):
    response = _Response({"ok": True})
    response._raw = b"{invalid"
    monkeypatch.setattr(telegram_api.urllib.request, "urlopen", lambda *a, **k: response)

    with pytest.raises(telegram_api.TelegramAPIError, match="invalid JSON") as caught:
        telegram_api.request("secret", "sendMessage")

    assert caught.value.retryable is True


@pytest.mark.parametrize("status", [401, 403, 409])
def test_permanent_http_errors_are_fatal(monkeypatch, status):
    body = json.dumps({
        "ok": False,
        "error_code": status,
        "description": "permanent",
    }).encode("utf-8")

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://api.telegram.org/redacted",
            status,
            "failure",
            {},
            io.BytesIO(body),
        )

    monkeypatch.setattr(telegram_api.urllib.request, "urlopen", fail)
    with pytest.raises(telegram_api.TelegramAPIError) as caught:
        telegram_api.request("secret", "getUpdates")

    assert caught.value.error_code == status
    assert caught.value.retryable is False
    assert caught.value.fatal is True


def test_server_error_is_retryable(monkeypatch):
    body = json.dumps({
        "ok": False,
        "error_code": 503,
        "description": "temporarily unavailable",
    }).encode("utf-8")

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://api.telegram.org/redacted",
            503,
            "failure",
            {},
            io.BytesIO(body),
        )

    monkeypatch.setattr(telegram_api.urllib.request, "urlopen", fail)
    with pytest.raises(telegram_api.TelegramAPIError) as caught:
        telegram_api.request("secret", "getUpdates")

    assert caught.value.retryable is True
    assert caught.value.fatal is False


def test_get_updates_propagates_transport_error(monkeypatch):
    failure = telegram_api.TelegramAPIError("offline", retryable=True)

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(telegram_api, "request", fail)
    with pytest.raises(telegram_api.TelegramAPIError) as caught:
        telegram_api.get_updates("token", 0)
    assert caught.value is failure


def test_send_message_retries_transient_errors_and_returns_result(monkeypatch):
    calls = []
    outcomes = [
        telegram_api.TelegramAPIError("timeout", retryable=True),
        telegram_api.TelegramAPIError(
            "rate limited",
            error_code=429,
            retry_after=2,
            retryable=True,
        ),
        {"message_id": 42},
    ]

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    sleeps = []
    monkeypatch.setattr(telegram_api, "request", request)
    result = telegram_api.send_message(
        "token",
        123,
        "hello",
        max_attempts=3,
        backoff_seconds=0.25,
        _sleep=sleeps.append,
    )

    assert result == telegram_api.SendResult(
        ok=True,
        chunks_sent=1,
        attempts=3,
        message_ids=(42,),
    )
    assert sleeps == [0.25, 2]
    assert calls[-1][0][2] == {"chat_id": 123, "text": "hello"}
    assert "parse_mode" not in calls[-1][0][2]


def test_send_message_does_not_retry_permanent_failure(monkeypatch):
    calls = 0

    def request(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise telegram_api.TelegramAPIError(
            "conflict",
            error_code=409,
            retryable=False,
            fatal=True,
        )

    monkeypatch.setattr(telegram_api, "request", request)
    with pytest.raises(telegram_api.TelegramAPIError):
        telegram_api.send_message("token", 123, "hello", _sleep=lambda _: None)
    assert calls == 1


def test_unicode_chunking_preserves_common_clusters_and_progress():
    text = "a" * 4095 + "👋🏽" + "b" * 4094 + "👨‍👩" + "🇪🇸"
    chunks = telegram_api._chunks(text)

    assert "".join(chunks) == text
    assert all(0 < len(chunk) <= telegram_api.TELEGRAM_MAX_MSG for chunk in chunks)
    assert not any(chunk.endswith(("👋", "\u200d", "🇪")) for chunk in chunks[:-1])

    pathological = "a" + "\u0301" * (telegram_api.TELEGRAM_MAX_MSG + 10)
    pathological_chunks = telegram_api._chunks(pathological)
    assert "".join(pathological_chunks) == pathological
    assert all(pathological_chunks)


def test_single_bot_lock_is_token_scoped_and_file_persists(tmp_path):
    first = TelegramLock("same-token", tmp_path)
    contender = TelegramLock("same-token", tmp_path)
    other = TelegramLock("different-token", tmp_path)

    assert first.acquire() is True
    assert contender.acquire() is False
    assert other.acquire() is True
    assert "same-token" not in first.path.name

    first.release()
    first.release()
    assert first.path.exists()
    assert contender.acquire() is True

    contender.release()
    other.release()


def test_single_bot_lock_excludes_another_process(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    result = context.Queue()
    process = context.Process(
        target=_hold_lock,
        args=("shared-token", str(tmp_path), ready, release, result),
    )
    process.start()
    try:
        assert ready.wait(5)
        assert result.get(timeout=2) is True
        contender = TelegramLock("shared-token", tmp_path)
        assert contender.acquire() is False
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(2)

    assert process.exitcode == 0
    assert contender.acquire() is True
    contender.release()


def test_single_bot_lock_is_released_when_owner_process_dies(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    result = context.Queue()
    process = context.Process(
        target=_hold_lock_until_killed,
        args=("crashed-owner-token", str(tmp_path), ready, result),
    )
    process.start()
    contender = TelegramLock("crashed-owner-token", tmp_path)
    try:
        assert ready.wait(5)
        assert result.get(timeout=2) is True
        assert contender.acquire() is False
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)

    assert not process.is_alive()
    assert contender.acquire() is True
    contender.release()


def test_offset_store_is_atomic_and_synchronizes_on_every_startup(tmp_path):
    store = TelegramOffsetStore("token", tmp_path)
    offsets = []

    def fetch(offset):
        offsets.append(offset)
        return [{"update_id": 18}, {"update_id": 20}]

    assert store.load_or_synchronize(fetch) == 21
    assert store.read() == 21
    assert offsets == [-1]
    assert store.load_or_synchronize(fetch) == 21
    assert offsets == [-1, -1]
    assert not list(tmp_path.glob("*.tmp"))

    store.path.write_text("corrupt", encoding="ascii")
    assert store.load_or_synchronize(fetch) == 21
    assert offsets == [-1, -1, -1]


def test_offset_store_discards_commands_received_between_missions(tmp_path):
    store = TelegramOffsetStore("token", tmp_path)
    store.write(21)

    next_offset = store.load_or_synchronize(
        lambda offset: [{"update_id": 25}] if offset == -1 else [],
    )

    assert next_offset == 26
    assert store.read() == 26


def test_offset_store_does_not_reuse_historical_numeric_range(tmp_path):
    store = TelegramOffsetStore("token", tmp_path)
    store.write(50_000)

    next_offset = store.load_or_synchronize(
        lambda offset: [{"update_id": 7}] if offset == -1 else [],
    )

    assert next_offset == 8
    assert store.read() == 8


def test_token_hash_is_stable_and_token_is_not_exposed():
    assert token_hash("secret") == token_hash("secret")
    assert token_hash("secret") != token_hash("other")
    assert "secret" not in token_hash("secret")

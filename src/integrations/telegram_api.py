"""Small, synchronous client for the Telegram Bot API.

The module intentionally owns transport concerns only.  Callers get explicit
success values and typed failures; policy such as stopping a listener lives in
the listener itself.
"""

from __future__ import annotations

import json
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

TELEGRAM_MAX_MSG = 4096
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.5
DEFAULT_MAX_BACKOFF_SECONDS = 5.0

_PERMANENT_ERROR_CODES = frozenset({401, 403, 409})


class TelegramAPIError(RuntimeError):
    """A Telegram API, HTTP, protocol, or network failure.

    ``retryable`` tells bounded operations such as ``send_message`` whether
    another attempt is useful.  ``fatal`` marks configuration/lifecycle
    failures for which a long-polling listener should stop (invalid token,
    forbidden chat, or a conflicting getUpdates consumer).
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        retry_after: float | None = None,
        retryable: bool = False,
        fatal: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retry_after = retry_after
        self.retryable = retryable
        self.fatal = fatal


@dataclass(frozen=True)
class SendResult:
    """Successful result of sending all chunks of one logical message."""

    ok: bool
    chunks_sent: int
    attempts: int
    message_ids: tuple[int, ...] = ()


def _is_regional_indicator(ch: str) -> bool:
    return "\U0001f1e6" <= ch <= "\U0001f1ff"


def _is_cluster_extension(ch: str) -> bool:
    codepoint = ord(ch)
    return (
        unicodedata.category(ch) in {"Mn", "Mc", "Me"}
        or ch in {"\ufe0e", "\ufe0f"}
        or "\U0001f3fb" <= ch <= "\U0001f3ff"
        or 0xE0020 <= codepoint <= 0xE007F
    )


def _splits_unicode_cluster(text: str, boundary: int) -> bool:
    """Return whether ``boundary`` cuts a common Unicode grapheme sequence.

    This deliberately covers the sequences most relevant to Telegram output:
    combining marks, variation selectors, skin tones, flags, and ZWJ emoji.
    It is not intended to replace the full Unicode grapheme-break algorithm.
    """

    if boundary <= 0 or boundary >= len(text):
        return False

    left = text[boundary - 1]
    right = text[boundary]
    if _is_cluster_extension(right):
        return True
    if left == "\u200d" or right == "\u200d":
        return True
    if left == "\r" and right == "\n":
        return True
    if _is_regional_indicator(right):
        preceding = 0
        pos = boundary - 1
        while pos >= 0 and _is_regional_indicator(text[pos]):
            preceding += 1
            pos -= 1
        return preceding % 2 == 1
    return False


def _safe_chunk_boundary(text: str, boundary: int, start: int = 0) -> int:
    """Move an absolute boundary left without ever preventing progress."""

    if start < 0:
        raise ValueError("start must be non-negative")
    boundary = min(max(boundary, start), len(text))
    if boundary >= len(text):
        return len(text)

    original = boundary
    while boundary > start and _splits_unicode_cluster(text, boundary):
        boundary -= 1

    # A pathological cluster can be longer than Telegram's limit.  Splitting
    # it is preferable to an infinite loop; the caller still makes progress.
    return original if boundary <= start else boundary


def _chunks(text: str, limit: int = TELEGRAM_MAX_MSG) -> tuple[str, ...]:
    if limit <= 0:
        raise ValueError("chunk limit must be positive")
    if not text:
        raise ValueError("Telegram messages cannot be empty")

    result: list[str] = []
    start = 0
    while start < len(text):
        end = _safe_chunk_boundary(text, start + limit, start)
        if end <= start:  # Defensive invariant: chunking is always monotonic.
            end = min(start + limit, len(text))
        result.append(text[start:end])
        start = end
    return tuple(result)


def _coerce_retry_after(value: object) -> float | None:
    try:
        retry_after = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return max(0.0, retry_after)


def _error_from_payload(
    payload: Mapping[str, Any] | None,
    *,
    http_status: int | None = None,
    retry_after_header: object = None,
) -> TelegramAPIError:
    data = payload or {}
    api_code = data.get("error_code")
    error_code = api_code if isinstance(api_code, int) else http_status
    description = data.get("description")
    if not isinstance(description, str) or not description:
        description = "Telegram request failed"

    parameters = data.get("parameters")
    retry_after: float | None = None
    if isinstance(parameters, Mapping):
        retry_after = _coerce_retry_after(parameters.get("retry_after"))
    if retry_after is None:
        retry_after = _coerce_retry_after(retry_after_header)

    retryable = error_code == 429 or (
        isinstance(error_code, int) and 500 <= error_code <= 599
    )
    return TelegramAPIError(
        description,
        error_code=error_code,
        retry_after=retry_after,
        retryable=retryable,
        fatal=error_code in _PERMANENT_ERROR_CODES,
    )


def _response_status(response: object) -> int | None:
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status
    getcode = getattr(response, "getcode", None)
    if callable(getcode):
        value = getcode()
        if isinstance(value, int):
            return value
    return None


def _decode_response(response: object, status: int | None) -> Mapping[str, Any]:
    read = getattr(response, "read", None)
    raw = read() if callable(read) else b""
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise TelegramAPIError(
            "Telegram returned an empty response",
            error_code=status,
            retryable=True,
        )
    try:
        decoded = json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelegramAPIError(
            "Telegram returned invalid JSON",
            error_code=status,
            retryable=True,
        ) from exc
    if not isinstance(decoded, Mapping):
        raise TelegramAPIError(
            "Telegram returned an invalid response object",
            error_code=status,
            retryable=True,
        )
    return decoded


def request(
    token: str,
    method: str,
    params: Mapping[str, object] | None = None,
    *,
    timeout: float = 10,
    http_method: str = "POST",
) -> Any:
    """Perform one validated Telegram Bot API request.

    The function never retries.  This keeps long-polling cancellation and
    listener backoff under the caller's control; bounded retry is layered on
    top by ``send_message``.
    """

    if not token:
        raise ValueError("Telegram token is required")
    if not method:
        raise ValueError("Telegram method is required")

    url = f"https://api.telegram.org/bot{token}/{method}"
    encoded = urllib.parse.urlencode(params or {}, doseq=True)
    data: bytes | None
    if http_method.upper() == "GET":
        if encoded:
            url = f"{url}?{encoded}"
        data = None
    else:
        data = encoded.encode("utf-8")

    response: object | None = None
    try:
        response = urllib.request.urlopen(url, data=data, timeout=timeout)
        status = _response_status(response)
        payload = _decode_response(response, status)
        if status is not None and status >= 400:
            raise _error_from_payload(payload, http_status=status)
        if payload.get("ok") is not True:
            raise _error_from_payload(payload, http_status=status)
        return payload.get("result")
    except TelegramAPIError:
        raise
    except urllib.error.HTTPError as exc:
        payload: Mapping[str, Any] | None = None
        try:
            raw = exc.read()
            decoded = json.loads(raw.decode("utf-8")) if raw else None
            if isinstance(decoded, Mapping):
                payload = decoded
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        retry_header = exc.headers.get("Retry-After") if exc.headers else None
        raise _error_from_payload(
            payload,
            http_status=exc.code,
            retry_after_header=retry_header,
        ) from exc
    except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
        raise TelegramAPIError(
            "Telegram request timed out or could not connect",
            retryable=True,
        ) from exc
    except OSError as exc:
        raise TelegramAPIError(
            "Telegram transport failed",
            retryable=True,
        ) from exc
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def get_updates(
    token: str,
    offset: int,
    timeout: int = 30,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch updates once and propagate typed transport/API failures."""

    params: dict[str, object] = {"offset": offset, "timeout": timeout}
    if limit is not None:
        params["limit"] = limit
    result = request(
        token,
        "getUpdates",
        params,
        timeout=timeout + 5,
        http_method="GET",
    )
    if not isinstance(result, list):
        raise TelegramAPIError(
            "Telegram getUpdates returned a non-list result",
            retryable=True,
        )
    return [item for item in result if isinstance(item, dict)]


def _request_with_retry(
    token: str,
    method: str,
    params: Mapping[str, object],
    *,
    timeout: float,
    max_attempts: int,
    backoff_seconds: float,
    max_backoff_seconds: float,
    sleep: Callable[[float], None],
) -> tuple[Any, int]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    for attempt in range(1, max_attempts + 1):
        try:
            return request(token, method, params, timeout=timeout), attempt
        except TelegramAPIError as exc:
            if not exc.retryable or attempt >= max_attempts:
                raise
            delay = (
                exc.retry_after
                if exc.retry_after is not None
                else backoff_seconds * (2 ** (attempt - 1))
            )
            sleep(min(max(0.0, delay), max(0.0, max_backoff_seconds)))
    raise AssertionError("retry loop exhausted without returning or raising")


def send_message(
    token: str,
    chat_id: str | int,
    text: str,
    *,
    timeout: float = 10,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
    _sleep: Callable[[float], None] = time.sleep,
) -> SendResult:
    """Send a plain-text logical message, retrying transient failures."""

    chunks = _chunks(text)
    attempts = 0
    message_ids: list[int] = []
    for chunk in chunks:
        result, used_attempts = _request_with_retry(
            token,
            "sendMessage",
            {"chat_id": chat_id, "text": chunk},
            timeout=timeout,
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
            sleep=_sleep,
        )
        attempts += used_attempts
        if isinstance(result, Mapping):
            message_id = result.get("message_id")
            if isinstance(message_id, int):
                message_ids.append(message_id)

    return SendResult(
        ok=True,
        chunks_sent=len(chunks),
        attempts=attempts,
        message_ids=tuple(message_ids),
    )

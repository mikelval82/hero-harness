import json
from unittest.mock import MagicMock

import pytest

import src.integrations.notifier as notifier_mod
from src.integrations.notifier import (
    Notifier,
    compute_notify_prefix,
    notify,
    notify_result,
    PROJECT_COLORS,
)


class TestComputeNotifyPrefix:

    def test_deterministic(self):
        a = compute_notify_prefix("myproject")
        b = compute_notify_prefix("myproject")
        assert a == b

    def test_contains_name(self):
        assert "myproject" in compute_notify_prefix("myproject")

    def test_contains_emoji(self):
        result = compute_notify_prefix("test")
        assert any(e in result for e in PROJECT_COLORS)


class TestNotify:

    def test_sends_telegram(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
        import src.integrations.telegram_api as _api
        calls = []
        monkeypatch.setattr(_api, "send_message", lambda t, c, m: calls.append((t, c, m)))
        notify("hello")
        assert len(calls) == 1
        assert calls[0][2] == "hello"

    def test_no_telegram(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        import src.integrations.telegram_api as _api
        calls = []
        monkeypatch.setattr(_api, "send_message", lambda t, c, m: calls.append(1))
        notify("hello")
        assert len(calls) == 0

    def test_prefix(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
        import src.integrations.telegram_api as _api
        calls = []
        monkeypatch.setattr(_api, "send_message", lambda t, c, m: calls.append(m))
        notify("hello", prefix="[PRJ]")
        assert len(calls) == 1
        assert "[PRJ]" in calls[0]
        assert "hello" in calls[0]

    def test_truncation(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
        import src.integrations.telegram_api as _api
        calls = []
        monkeypatch.setattr(_api, "send_message", lambda t, c, m: calls.append(m))
        notify("x" * 5000)
        assert len(calls) == 1
        assert len(calls[0]) <= 4000


class TestNotifyResult:

    def test_blocked(self, tmp_path):
        h = tmp_path / "harness"
        h.mkdir()
        tasks = [{"id": "1", "status": "pending"}]
        (h / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
        (h / "mission-report.md").write_text("Report\n", encoding="utf-8")
        calls = []
        notify_result("task", "branch", h, blocked_at="spec", notify_fn=calls.append)
        assert len(calls) == 1
        assert "BLOCKED" in calls[0]

    def test_complete(self, tmp_path):
        h = tmp_path / "harness"
        h.mkdir()
        tasks = [{"id": "1", "status": "completed"}]
        (h / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
        calls = []
        notify_result("task", "branch", h, blocked_at="", notify_fn=calls.append)
        assert len(calls) == 1
        assert "COMPLETE" in calls[0]

    def test_partial(self, tmp_path):
        h = tmp_path / "harness"
        h.mkdir()
        tasks = [{"id": "1", "status": "completed"}, {"id": "2", "status": "failed"}]
        (h / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
        calls = []
        notify_result("task", "branch", h, blocked_at="", notify_fn=calls.append)
        assert "PARTIAL" in calls[0]


class TestNotifierClass:

    def test_send(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        n = Notifier(prefix="[T]")
        n.send("hi")

    def test_notify_result(self, tmp_path, monkeypatch):
        h = tmp_path / "harness"
        h.mkdir()
        tasks = [{"id": "1", "status": "completed"}]
        (h / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
        calls = []
        monkeypatch.setattr(notifier_mod, "notify", lambda msg, prefix="": calls.append(msg))
        n = Notifier(prefix="[T]")
        n.notify_result("task", "branch", h)
        assert len(calls) == 1

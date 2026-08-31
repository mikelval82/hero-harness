from __future__ import annotations

import os


# A provider-facing process must never inherit credentials or control-plane
# switches from the process that runs HERO.  Keep the list explicit for the
# documented providers and also remove common credential-shaped names so a
# future provider cannot silently leak a new token to Bash.
HERO_CREDENTIAL_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "TELEGRAM_TOKEN",
        "TELEGRAM_CHAT_ID",
        "CLAUDE_HARNESS",
    }
)
_CREDENTIAL_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "WORKER")


def sanitized_child_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment suitable for a target-project child process.

    This is credential isolation, not an operating-system sandbox: the child
    still has the permissions of the account that launched HERO.
    """

    child = dict(os.environ if source is None else source)
    for key in tuple(child):
        normalized = key.upper()
        if normalized in HERO_CREDENTIAL_KEYS or any(marker in normalized for marker in _CREDENTIAL_MARKERS):
            child.pop(key, None)
    return child

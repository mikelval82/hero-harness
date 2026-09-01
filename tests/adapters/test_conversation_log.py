from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mission_orchestrator.adapters.conversation.sqlite_log import SqliteConversationLog
from mission_orchestrator.domain.conversation import ConversationRole


class ConversationLogTest(unittest.TestCase):
    def test_transcript_is_ordered_and_incremental(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            log = SqliteConversationLog(Path(raw) / "conversation.db")
            first = log.append(ConversationRole.AGENT, "What matters most?", phase="grill")
            second = log.append(ConversationRole.HUMAN, "Reliability", phase="grill")

            self.assertEqual(first.sequence, 1)
            self.assertEqual(second.sequence, 2)
            self.assertEqual(
                [message.role for message in log.messages()],
                [ConversationRole.AGENT, ConversationRole.HUMAN],
            )
            self.assertEqual(
                [message.content for message in log.messages(after_sequence=1)],
                ["Reliability"],
            )


if __name__ == "__main__":
    unittest.main()
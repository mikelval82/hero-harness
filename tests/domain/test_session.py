from __future__ import annotations

import unittest

from mission_orchestrator.domain.session import MissionSession, MissionStage, SessionAction


class MissionSessionTest(unittest.TestCase):
    def test_valid_transition_increments_revision_and_exposes_actions(self) -> None:
        draft = MissionSession("mission-1")

        researching = draft.move_to(MissionStage.RESEARCHING, active_phase="research")
        review = researching.move_to(MissionStage.RESEARCH_REVIEW)

        self.assertEqual(review.revision, 2)
        self.assertEqual(review.stage, MissionStage.RESEARCH_REVIEW)
        self.assertEqual(
            review.allowed_actions,
            (SessionAction.RUN_RESEARCH, SessionAction.START_GRILL),
        )

    def test_invalid_transition_is_rejected(self) -> None:
        session = MissionSession("mission-1")

        with self.assertRaisesRegex(ValueError, "draft -> executing"):
            session.move_to(MissionStage.EXECUTING)

    def test_json_round_trip_keeps_authoritative_state(self) -> None:
        session = MissionSession("mission-1").move_to(
            MissionStage.RESEARCHING,
            active_phase="research",
        )

        restored = MissionSession.from_json(session.to_json())

        self.assertEqual(restored, session)
        self.assertEqual(restored.to_json()["allowed_actions"], [])


if __name__ == "__main__":
    unittest.main()
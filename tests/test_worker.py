from __future__ import annotations

import unittest

from mission_orchestrator.worker import parse_args


class WorkerArgumentsTest(unittest.TestCase):
    def test_worker_defaults_to_ephemeral_loopback_api(self) -> None:
        args = parse_args(["--project", "."])

        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 0)
        self.assertEqual(args.mode, "full")
        self.assertIsNone(args.provider)

    def test_worker_accepts_deepseek_provider_and_model(self) -> None:
        args = parse_args(
            ["--project", ".", "--provider", "deepseek", "--model", "deepseek-v4-flash"]
        )

        self.assertEqual(args.provider, "deepseek")
        self.assertEqual(args.model, "deepseek-v4-flash")

    def test_worker_accepts_spec_plan_alias(self) -> None:
        args = parse_args(["--project", ".", "--mode", "spec-plan"])
        self.assertEqual(args.mode, "spec-plan")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from mission_orchestrator.worker import parse_args


class WorkerArgumentsTest(unittest.TestCase):
    def test_worker_defaults_to_ephemeral_loopback_api(self) -> None:
        args = parse_args(["--project", "."])

        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 0)
        self.assertEqual(args.mode, "full")


if __name__ == "__main__":
    unittest.main()
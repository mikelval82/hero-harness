from __future__ import annotations

import os
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent.parent
CLAUDE_HOME = SRC_DIR.parent
AGENTS_DIR = CLAUDE_HOME / "agents"
PROMPTS_DIR = CLAUDE_HOME / "prompts"
HARNESS = Path(os.environ.get("CLAUDE_HARNESS", "/tmp/claude-harness"))

if str(CLAUDE_HOME) not in sys.path:
    sys.path.insert(0, str(CLAUDE_HOME))

# Contributing to Claude Harness

Thanks for your interest in improving Claude Harness! This document explains how to set
up your environment, the conventions we follow, and how to submit changes.

## Getting started

1. Fork and clone the repository.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   pip install pytest
   ```
3. Copy `.env.example` to `.env` and add your `ANTHROPIC_API_KEY`.

## Running the tests

```bash
python -m pytest src/tests -q
python -m pytest benchmark -q
```

All tests must pass before opening a pull request.

## Coding conventions

This project keeps a **static code graph** (tree-sitter) over `src/`. To keep the graph
accurate, production code follows the rules in [`src/CLAUDE.md`](src/CLAUDE.md):

- Classes and functions must be **top-level** (no nested definitions).
- Imports must be **absolute** (e.g. `from src.core.gate import check_gate`).
- Calls must be **direct** (avoid dynamic dispatch / call-through-variable).
- Inheritance must be **explicit**.

Other conventions:

- Specifications use **EARS** syntax; architectural decisions use **ADR** format.
- Prompt templates live in `prompts/` with the `-prompt.md` suffix.

## Submitting changes

1. Create a feature branch: `git checkout -b feat/my-change`.
2. Make your change with focused commits and clear messages.
3. Add or update tests.
4. Run the full test suite.
5. Open a pull request describing **what** changed and **why**.

## Reporting issues

Please use the issue templates and include reproduction steps, expected vs. actual
behaviour, and your environment (OS, Python version).

By contributing you agree that your contributions will be licensed under the MIT License.

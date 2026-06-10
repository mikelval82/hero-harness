from pathlib import Path

from src.harness.project_memory import (
    HARNESS_MEMORY_FILE,
    HARNESS_MEMORY_PATH_FILE,
    MEMORY_FILE,
    default_project_memory,
    ensure_project_memory,
    project_memory_key,
    project_memory_path,
    stage_project_memory,
    sync_project_memory,
)


def test_project_memory_key_is_stable_and_path_specific(tmp_path):
    p1 = tmp_path / "repo"
    p2 = tmp_path / "other" / "repo"
    p1.mkdir()
    p2.mkdir(parents=True)

    assert project_memory_key(p1) == project_memory_key(p1)
    assert project_memory_key(p1) != project_memory_key(p2)
    assert project_memory_key(p1).startswith("repo-")


def test_ensure_project_memory_creates_policy_file(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()

    path = ensure_project_memory(project, base_dir=tmp_path / "memory")

    assert path.name == MEMORY_FILE
    text = path.read_text(encoding="utf-8")
    assert "# Project Memory" in text
    assert "## Policy" in text
    assert "Do not store secrets" in text
    assert "## Conventions" in text


def test_stage_project_memory_copies_to_harness_and_writes_pointer(tmp_path):
    project = tmp_path / "repo"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()

    info = stage_project_memory(project, harness, base_dir=tmp_path / "memory")

    staged = harness / HARNESS_MEMORY_FILE
    pointer = harness / HARNESS_MEMORY_PATH_FILE
    assert info["staged"] == staged
    assert info["persistent"] == project_memory_path(project, base_dir=tmp_path / "memory")
    assert staged.read_text(encoding="utf-8") == info["persistent"].read_text(encoding="utf-8")
    assert pointer.read_text(encoding="utf-8") == str(info["persistent"])


def test_stage_project_memory_preserves_resume_copy(tmp_path):
    project = tmp_path / "repo"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    stage_project_memory(project, harness, base_dir=tmp_path / "memory")
    staged = harness / HARNESS_MEMORY_FILE
    staged.write_text("local mission edits\n", encoding="utf-8")

    stage_project_memory(project, harness, base_dir=tmp_path / "memory", preserve_existing=True)

    assert staged.read_text(encoding="utf-8") == "local mission edits\n"


def test_sync_project_memory_copies_harness_memory_to_persistent(tmp_path):
    project = tmp_path / "repo"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    info = stage_project_memory(project, harness, base_dir=tmp_path / "memory")
    (harness / HARNESS_MEMORY_FILE).write_text("updated memory\n", encoding="utf-8")

    assert sync_project_memory(harness) is True

    assert info["persistent"].read_text(encoding="utf-8") == "updated memory\n"


def test_sync_project_memory_returns_false_without_staged_file(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()

    assert sync_project_memory(harness) is False


def test_default_project_memory_mentions_project_path(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()

    text = default_project_memory(project)

    assert "project_name: repo" in text
    assert str(Path(project).resolve()) in text

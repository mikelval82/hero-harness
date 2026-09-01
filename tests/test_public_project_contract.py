from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicProjectContractTests(unittest.TestCase):
    def test_distribution_metadata_matches_public_identity(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]

        self.assertEqual(project["name"], "hero-harness")
        self.assertEqual(project["license"], {"file": "LICENSE"})
        self.assertEqual(project["authors"], [{"name": "Mikel Val Calvo"}])
        self.assertEqual(
            project["urls"],
            {
                "Homepage": "https://github.com/mikelval82/hero-harness",
                "Repository": "https://github.com/mikelval82/hero-harness",
                "Issues": "https://github.com/mikelval82/hero-harness/issues",
            },
        )
        self.assertIn("License :: OSI Approved :: MIT License", project["classifiers"])
        self.assertIn("Programming Language :: Python :: 3.12", project["classifiers"])

    def test_public_files_describe_safe_configuration_boundaries(self) -> None:
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("DEEPSEEK_BASE_URL=https://api.deepseek.com", env_example)
        self.assertIn("TELEGRAM_TOKEN", env_example)
        self.assertNotIn("sk-", env_example.lower())
        self.assertIn("## Validación y límites de evidencia", readme)
        self.assertIn("no autentica ni contacta proveedores", readme)

    def test_public_contribution_files_exist(self) -> None:
        for relative in (
            "LICENSE",
            "CONTRIBUTING.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/ISSUE_TEMPLATE/bug_report.md",
            ".github/ISSUE_TEMPLATE/feature_request.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()

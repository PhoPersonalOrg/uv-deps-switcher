import os
import tempfile
import unittest
from pathlib import Path

from uv_deps_switcher.main import deploy_templates

FRAGMENT_NAMES = (
    "pyproject_template_dev.toml_fragment",
    "pyproject_template_external.toml_fragment",
    "pyproject_template_release.toml_fragment",
    "pyproject_template_workspace.toml_fragment",
)


def _write_pyproject(
    project_path: Path,
    *,
    dependencies: list[str],
    sources: dict[str, dict] | None = None,
) -> None:
    """Write a minimal pyproject.toml with optional [tool.uv.sources]."""
    lines = [
        "[project]",
        'name = "example"',
        'version = "0.1.0"',
        "dependencies = [",
    ]
    for dep in dependencies:
        lines.append(f'    "{dep}",')
    lines.append("]")

    if sources is not None:
        lines.extend(["", "[tool.uv.sources]"])
        for name, spec in sources.items():
            parts = []
            for key, value in spec.items():
                if isinstance(value, bool):
                    parts.append(f"{key} = {'true' if value else 'false'}")
                else:
                    parts.append(f'{key} = "{value}"')
            lines.append(f"{name} = {{ {', '.join(parts)} }}")

    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


class DeployTemplatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_prefix = os.environ.pop("ACTIVE_DEV_PATH_PREFIX", None)

    def tearDown(self) -> None:
        if self._original_prefix is not None:
            os.environ["ACTIVE_DEV_PATH_PREFIX"] = self._original_prefix
        else:
            os.environ.pop("ACTIVE_DEV_PATH_PREFIX", None)

    def _minimal_project(self, tmp: str) -> Path:
        project_path = Path(tmp) / "ExampleProject"
        _write_pyproject(
            project_path,
            dependencies=["phopylslhelper"],
            sources={"phopylslhelper": {"path": "../PhoPyLSLhelper", "editable": True}},
        )
        return project_path

    def test_deploy_templates_missing_pyproject_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "EmptyProject"
            project_path.mkdir()

            result = deploy_templates(project_path)

            self.assertFalse(result)
            self.assertFalse((project_path / "templating").exists())

    def test_deploy_templates_no_sources_or_dependencies_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "ExampleProject"
            _write_pyproject(project_path, dependencies=[])

            result = deploy_templates(project_path)

            self.assertFalse(result)
            self.assertFalse((project_path / "templating").exists())

    def test_deploy_templates_filters_to_dependency_intersection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "ExampleProject"
            _write_pyproject(
                project_path,
                dependencies=["phopylslhelper"],
                sources={
                    "phopylslhelper": {"path": "../PhoPyLSLhelper", "editable": True},
                    "neuropy": {"path": "../NeuroPy", "editable": True},
                },
            )

            result = deploy_templates(project_path)

            self.assertTrue(result)
            dev_content = (project_path / "templating" / FRAGMENT_NAMES[0]).read_text(encoding="utf-8")
            self.assertIn("phopylslhelper", dev_content)
            self.assertNotIn("neuropy", dev_content)

    def test_deploy_templates_writes_all_four_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = self._minimal_project(tmp)

            result = deploy_templates(project_path)

            self.assertTrue(result)
            templating_dir = project_path / "templating"
            self.assertTrue(templating_dir.is_dir())
            for name in FRAGMENT_NAMES:
                fragment_path = templating_dir / name
                self.assertTrue(fragment_path.is_file(), msg=f"missing {name}")
                content = fragment_path.read_text(encoding="utf-8")
                self.assertTrue(content.startswith("[tool.uv.sources]"), msg=f"{name} missing header")

    def test_deploy_templates_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = self._minimal_project(tmp)

            result = deploy_templates(project_path, dry_run=True)

            self.assertTrue(result)
            templating_dir = project_path / "templating"
            self.assertFalse(templating_dir.exists())
            for name in FRAGMENT_NAMES:
                self.assertFalse((project_path / "templating" / name).exists())

    def test_deploy_dev_fragment_substitutes_prefix_at_deploy_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = self._minimal_project(tmp)

            deploy_templates(project_path)

            dev_content = (project_path / "templating" / FRAGMENT_NAMES[0]).read_text(encoding="utf-8")
            self.assertIn('path = "../PhoPyLSLhelper"', dev_content)
            self.assertNotIn("{ACTIVE_DEV_PATH_PREFIX}", dev_content)

    def test_deploy_external_fragment_preserves_runtime_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = self._minimal_project(tmp)

            deploy_templates(project_path)

            external_content = (project_path / "templating" / FRAGMENT_NAMES[1]).read_text(encoding="utf-8")
            self.assertIn('path = "{ACTIVE_DEV_PATH_PREFIX}/PhoPyLSLhelper"', external_content)
            self.assertNotIn(project_path.parent.resolve().as_posix(), external_content)

    def test_deploy_dev_fragment_uses_env_prefix_at_deploy_time(self) -> None:
        os.environ["ACTIVE_DEV_PATH_PREFIX"] = "ACTIVE_DEV/"
        with tempfile.TemporaryDirectory() as tmp:
            project_path = self._minimal_project(tmp)

            deploy_templates(project_path)

            dev_content = (project_path / "templating" / FRAGMENT_NAMES[0]).read_text(encoding="utf-8")
            self.assertIn('path = "../ACTIVE_DEV/PhoPyLSLhelper"', dev_content)
            self.assertNotIn("{ACTIVE_DEV_PATH_PREFIX}", dev_content)

    def test_deploy_templates_uses_dependencies_when_no_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "ExampleProject"
            _write_pyproject(project_path, dependencies=["phopylslhelper"])

            result = deploy_templates(project_path)

            self.assertTrue(result)
            dev_content = (project_path / "templating" / FRAGMENT_NAMES[0]).read_text(encoding="utf-8")
            self.assertIn("phopylslhelper", dev_content)


if __name__ == "__main__":
    unittest.main()

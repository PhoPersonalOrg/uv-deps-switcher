import os
import tempfile
import unittest
from pathlib import Path

from uv_deps_switcher.main import (
    get_active_dev_path_prefix,
    read_template,
    render_template,
)


class PathPrefixTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_prefix = os.environ.pop("ACTIVE_DEV_PATH_PREFIX", None)

    def tearDown(self) -> None:
        if self._original_prefix is not None:
            os.environ["ACTIVE_DEV_PATH_PREFIX"] = self._original_prefix
        else:
            os.environ.pop("ACTIVE_DEV_PATH_PREFIX", None)

    def test_dev_prefix_does_not_auto_detect_active_dev(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "ACTIVE_DEV" / "ExampleProject"
            project_path.mkdir(parents=True)

            self.assertEqual(get_active_dev_path_prefix(project_path, auto_detect_absolute=False), "")

    def test_external_prefix_can_auto_detect_active_dev(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            active_dev_path = Path(tmp) / "ACTIVE_DEV"
            project_path = active_dev_path / "ExampleProject"
            project_path.mkdir(parents=True)

            self.assertEqual(
                get_active_dev_path_prefix(project_path, auto_detect_absolute=True),
                active_dev_path.resolve().as_posix(),
            )

    def test_read_template_dev_uses_empty_default_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "ACTIVE_DEV" / "ExampleProject"
            templating_path = project_path / "templating"
            templating_path.mkdir(parents=True)
            (templating_path / "pyproject_template_dev.toml_fragment").write_text(
                (
                    "[tool.uv.sources]\n"
                    'phopylslhelper = { path = "../{ACTIVE_DEV_PATH_PREFIX}PhoPyLSLhelper", editable = true }\n'
                ),
                encoding="utf-8",
            )

            content = read_template(project_path, "dev")

            self.assertIsNotNone(content)
            self.assertIn('path = "../PhoPyLSLhelper"', content)
            self.assertNotIn("ACTIVE_DEV", content)

    def test_render_dev_template_preserves_runtime_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "ACTIVE_DEV" / "ExampleProject"
            project_path.mkdir(parents=True)

            content = render_template(
                "pyproject_template_dev.toml_fragment.j2",
                {"phopylslhelper"},
                project_path,
            )

            self.assertIn('path = "../{ACTIVE_DEV_PATH_PREFIX}PhoPyLSLhelper"', content)
            self.assertNotIn(project_path.parent.resolve().as_posix(), content)


if __name__ == "__main__":
    unittest.main()

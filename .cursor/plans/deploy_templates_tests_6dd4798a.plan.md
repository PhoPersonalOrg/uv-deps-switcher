---
name: Deploy templates tests
overview: "Add a new unittest module covering `deploy_templates()` end-to-end: error paths, dependency filtering, dry-run behavior, file output, and dev vs external prefix handling in deployed fragments."
todos:
  - id: create-test-module
    content: Create tests/test_deploy_templates.py with helper to write minimal pyproject.toml fixtures
    status: completed
  - id: error-and-filter-tests
    content: Add tests for missing pyproject, empty deps/sources, and dependency intersection filtering
    status: completed
  - id: deploy-output-tests
    content: Add tests for writes-all-four-fragments, dry-run no-write, and dev/external prefix behavior in deployed files
    status: completed
  - id: run-tests
    content: Run unittest discover and confirm all deploy template tests pass
    status: completed
isProject: false
---

# Unit Tests for Template Deployment

## Context

[`deploy_templates()`](src/uv_deps_switcher/main.py) reads a project's `pyproject.toml`, derives `include_deps` from `[tool.uv.sources]` intersected with `[project.dependencies]`, renders four Jinja2 fragments, and writes them under `templating/`. Existing tests in [`tests/test_path_prefix.py`](tests/test_path_prefix.py) cover prefix rendering in isolation but not the deployment orchestration.

## New test file

Create [`tests/test_deploy_templates.py`](tests/test_deploy_templates.py) using `unittest` + `tempfile` (same style as existing tests). Import:

```python
from uv_deps_switcher.main import deploy_templates
```

Add a small helper to build a temp project:

```python
def _write_pyproject(project_path: Path, *, dependencies: list[str], sources: dict | None = None) -> None:
    # Minimal valid pyproject.toml with [project.dependencies] and optional [tool.uv.sources]
```

Use `phopylslhelper` as the primary fixture dep — it exists in all four J2 templates and maps cleanly to template conditionals.

## Test cases

| Test | Asserts |
|------|---------|
| `test_deploy_templates_missing_pyproject_returns_false` | Empty temp dir, no `pyproject.toml` → `False`, no `templating/` created |
| `test_deploy_templates_no_sources_or_dependencies_returns_false` | Minimal pyproject with no deps and no sources → `False` |
| `test_deploy_templates_filters_to_dependency_intersection` | Sources for `phopylslhelper` + `neuropy`; dependencies list only `phopylslhelper` → deployed dev fragment contains `phopylslhelper`, does **not** contain `neuropy` |
| `test_deploy_templates_writes_all_four_fragments` | Valid pyproject → `True`; all four files exist under `templating/`; each starts with `[tool.uv.sources]` |
| `test_deploy_templates_dry_run_does_not_write_files` | `dry_run=True` → `True`; `templating/` dir and fragment files must not exist |
| `test_deploy_dev_fragment_substitutes_prefix_at_deploy_time` | Deploy with unset prefix → dev fragment has `../PhoPyLSLhelper`, no `{ACTIVE_DEV_PATH_PREFIX}` |
| `test_deploy_external_fragment_preserves_runtime_placeholder` | Deploy → external fragment has `{ACTIVE_DEV_PATH_PREFIX}/PhoPyLSLhelper`, no absolute path baked in |
| `test_deploy_dev_fragment_uses_env_prefix_at_deploy_time` | Set `ACTIVE_DEV_PATH_PREFIX=ACTIVE_DEV/` during deploy → dev fragment has `../ACTIVE_DEV/PhoPyLSLhelper` |

Optional (include if straightforward): `test_deploy_templates_uses_dependencies_when_no_sources` — pyproject with deps but empty/missing `[tool.uv.sources]` still deploys fragments for listed deps.

## Fixture example

Minimal pyproject for happy-path tests:

```toml
[project]
name = "example"
version = "0.1.0"
dependencies = ["phopylslhelper"]

[tool.uv.sources]
phopylslhelper = { path = "../PhoPyLSLhelper", editable = true }
```

## Prefix env handling

For tests that set `ACTIVE_DEV_PATH_PREFIX`, use the same `setUp`/`tearDown` pattern as [`tests/test_path_prefix.py`](tests/test_path_prefix.py) (save/restore env var).

## Verification

```powershell
$env:PYTHONPATH="src"; python -m unittest tests.test_deploy_templates -v
$env:PYTHONPATH="src"; python -m unittest discover -s tests -v
```

No changes to production code unless a test reveals a bug.

## Out of scope

- CLI argument parsing for `deploy-templates` subcommand
- Release-template git URL inference from local repos (static J2 URLs)
- Capturing stdout/stderr from deploy print statements (not required for correctness)

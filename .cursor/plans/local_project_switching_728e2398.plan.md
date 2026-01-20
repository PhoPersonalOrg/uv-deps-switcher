---
name: Local Project Switching
overview: Add support for running `switch-uv-deps dev` or `switch-uv-deps release` directly in a project folder to switch only that project's dependencies without needing to specify --group, --all, or --repo flags.
todos:
  - id: add-helper
    content: Add is_valid_project() helper function to main.py
    status: completed
  - id: modify-logic
    content: Update target selection logic to auto-detect current directory as valid project
    status: completed
    dependencies:
      - add-helper
  - id: update-help
    content: Update CLI epilog examples and error message
    status: completed
    dependencies:
      - modify-logic
  - id: update-readme
    content: Add documentation for local project switching in README.md
    status: completed
    dependencies:
      - modify-logic
---

# Local Project Dependency Switching

## Overview

Allow running `switch-uv-deps dev` or `switch-uv-deps release` in a valid project folder (one containing `templating/` with both template files) to switch dependencies for only that local project, ignoring defined groups.

## Current Behavior

Currently, running `switch-uv-deps dev` without `--group`, `--all`, or `--repo` produces:

```
Error: Must specify --group, --all, or --repo
```

## New Behavior

When no target flag is provided:

1. Check if the **current working directory** is a valid project (contains both `templating/pyproject_template_dev.toml_fragment` and `templating/pyproject_template_release.toml_fragment`)
2. If valid: switch that project's dependencies directly
3. If not valid: fall back to the existing error message

## Implementation

Modify [src/uv_deps_switcher/main.py](src/uv_deps_switcher/main.py):

1. **Add helper function** to check if a directory is a valid project:
```python
def is_valid_project(project_path: Path) -> bool:
    """Check if a directory is a valid project with templating."""
    templating_dir = project_path / "templating"
    dev_template = templating_dir / "pyproject_template_dev.toml_fragment"
    release_template = templating_dir / "pyproject_template_release.toml_fragment"
    return dev_template.exists() and release_template.exists()
```

2. **Modify the target selection logic** (around line 354) - when no flag is provided, check current directory:
```python
else:
    # No flag specified - check if current directory is a valid project
    cwd = Path.cwd()
    if is_valid_project(cwd):
        repos_to_switch = [cwd]
    else:
        print("Error: Must specify --group, --all, or --repo, or run from within a valid project folder", file=sys.stderr)
        return 1
```

3. **Update CLI help** to document the new behavior in the epilog examples

4. **Update README.md** to document the new local project switching feature
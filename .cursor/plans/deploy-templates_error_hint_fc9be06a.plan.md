---
name: deploy-templates error hint
overview: Extend the local-mode validation error in `main.py` with a actionable hint pointing users to `uv-deps-switcher deploy-templates` when templating files are missing.
todos:
  - id: update-error-message
    content: Add deploy-templates hint (conditional on pyproject.toml) to local-mode error in main.py lines 915-917
    status: completed
isProject: false
---

# Add deploy-templates hint to invalid-project error

## Context

When running `uv-deps-switcher dev` (or any mode) **without** `--group`, `--all`, or `--repo`, the tool requires the current directory to pass `is_valid_project()` — i.e. both template files must exist under `templating/`:

- `pyproject_template_dev.toml_fragment`
- `pyproject_template_release.toml_fragment`

If not, it exits at [src/uv_deps_switcher/main.py](src/uv_deps_switcher/main.py) line 916 with only:

```
Error: Must specify --group, --all, or --repo, or run from within a valid project folder
```

You hit this in `bapun_sess_init_scripts` and resolved it with `deploy-templates`; the error should tell future users the same.

## Change

Update the `else` branch at lines 915–917 in [src/uv_deps_switcher/main.py](src/uv_deps_switcher/main.py):

**Before:**
```python
print("Error: Must specify --group, --all, or --repo, or run from within a valid project folder", file=sys.stderr)
return 1
```

**After (proposed):**
```python
print("Error: Must specify --group, --all, or --repo, or run from within a valid project folder", file=sys.stderr)
print("Hint: Run `uv-deps-switcher deploy-templates` in a UV project to create the required templating/ files.", file=sys.stderr)
return 1
```

`cwd` is already in scope on line 912, so no new variables are needed unless we want a conditional hint (see optional enhancement below).

## Optional enhancement (recommended)

Tailor the hint based on whether `pyproject.toml` exists in `cwd`:

- **Has `pyproject.toml`:** suggest running `deploy-templates` here (matches your workflow).
- **No `pyproject.toml`:** suggest `cd`ing to a UV project first, then `deploy-templates`.

This avoids suggesting a command that will immediately fail with "No pyproject.toml found" when the user is in the wrong directory.

```python
print("Error: Must specify --group, --all, or --repo, or run from within a valid project folder", file=sys.stderr)
if (cwd / "pyproject.toml").exists():
    print("Hint: Run `uv-deps-switcher deploy-templates` to create the required templating/ files.", file=sys.stderr)
else:
    print("Hint: cd to a UV project (with pyproject.toml) and run `uv-deps-switcher deploy-templates` to set up.", file=sys.stderr)
return 1
```

## Out of scope

- No README change unless you want docs kept in sync (the README already documents `deploy-templates` separately).
- No tests exist in this repo today; adding a test would be optional follow-up.
- No manual verification step.

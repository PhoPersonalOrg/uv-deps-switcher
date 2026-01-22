---
name: Rename CLI Tool
overview: Change the CLI command name from `switch-uv-deps` to `uv-deps-switcher` to match the package name.
todos: []
isProject: false
---

# Rename CLI Tool to Match Package Name

## Change Required

In [`pyproject.toml`](pyproject.toml), line 12:

```python
# Current
switch-uv-deps = "uv_deps_switcher.main:main"

# Change to
uv-deps-switcher = "uv_deps_switcher.main:main"
```

## Post-Change

After editing, run `uv sync` to reinstall the package with the new command name. The tool will then be available as `uv-deps-switcher` instead of `switch-uv-deps`.
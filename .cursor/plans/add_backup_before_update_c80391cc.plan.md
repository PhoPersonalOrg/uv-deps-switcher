---
name: Add Backup Before Update
overview: Add automatic backup of pyproject.toml to the project's templating/ folder before modifications, allowing users to revert changes if needed.
todos:
  - id: add-backup
    content: Add backup logic to update_pyproject_sources before writing changes
    status: completed
---

# Add Automatic Backup Before pyproject.toml Modification

## Change

Modify [`src/uv_deps_switcher/main.py`](src/uv_deps_switcher/main.py) to save a backup of each project's `pyproject.toml` to `templating/pyproject.toml.bak` before applying changes.

## Implementation

In `update_pyproject_sources()`, add backup logic before writing changes:

```python
# Before writing updated content, save backup
backup_path = pyproject_path.parent / "templating" / "pyproject.toml.bak"
if backup_path.parent.exists():
    import shutil
    shutil.copy2(pyproject_path, backup_path)
```

This will:

- Save backup to `project/templating/pyproject.toml.bak`
- Overwrite previous backup (simple naming)
- Only create backup if templating/ folder exists (which it should, since that's where templates come from)
- Skip backup in dry-run mode (no changes are made anyway)
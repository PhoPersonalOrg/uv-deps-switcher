---
name: deploy-templates default yes
overview: Make the explicit `deploy-templates` and `--deploy-templates` commands deploy without a confirmation prompt by default. The auto-deploy path when running a mode switch on a project missing templating files stays prompt-based unless `--yes` is passed.
todos:
  - id: remove-prompt
    content: Remove confirmation prompt block in deploy-templates CLI handler (main.py ~971-975)
    status: completed
  - id: verify
    content: Run test_deploy_templates and manual smoke test of deploy-templates / --deploy-templates
    status: completed
isProject: false
---

# deploy-templates defaults to --yes

## Current behavior

In [`src/uv_deps_switcher/main.py`](src/uv_deps_switcher/main.py), the dedicated deploy-templates handler prompts before writing files unless `--dry-run` or `-y`/`--yes`/`--force` is passed:

```971:975:src/uv_deps_switcher/main.py
        if not deploy_args.dry_run and not deploy_args.yes:
            response = input(f"Deploy templates to {cwd.name}? [y/N]: ")
            if response.lower() not in ["y", "yes"]:
                print("Cancelled")
                return 0
```

This is especially awkward for the flag form `uv-deps-switcher --deploy-templates`, which rejects additional arguments (lines 954–956), so users cannot pass `--yes` at all with that invocation.

The separate auto-deploy path (lines 1110–1129, triggered when running a mode switch on a project with `pyproject.toml` but missing templating) is **out of scope** per your choice — it will keep requiring `--yes` or interactive confirmation.

## Change

**Remove the confirmation block** (lines 971–975) from the deploy-templates command handler.

After this change:
- `uv-deps-switcher deploy-templates` deploys immediately
- `uv-deps-switcher --deploy-templates` deploys immediately (fixes the flag form)
- `uv-deps-switcher deploy-templates --dry-run` still previews only (unchanged; no prompt today either)
- `-y`/`--yes` on the deploy parser becomes a no-op but can stay for backward compatibility

No changes to:
- Main parser `--yes` behavior for mode switches
- Auto-deploy prompt when running `uv-deps-switcher <mode>` on an invalid/missing-templating project
- [`tests/test_deploy_templates.py`](tests/test_deploy_templates.py) — tests call `deploy_templates()` directly, not the CLI prompt path

## Optional doc touch-up

[`README.md`](README.md) Deploy Templates section (lines 165–177) does not mention a confirmation prompt today, so no README change is required. Optionally add a one-line note that deploy-templates runs non-interactively (unlike mode switches, which still prompt unless `--yes`).

## Verification

```bash
python -m unittest tests.test_deploy_templates
# From a UV project with pyproject.toml:
uv-deps-switcher deploy-templates          # should deploy without prompting
uv-deps-switcher --deploy-templates        # same, no extra args needed
uv-deps-switcher deploy-templates --dry-run  # still preview-only
```

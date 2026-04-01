# UV Dependency Switcher

A Python package that automatically switches UV dependency sources between dev (local editable paths) and release (git URLs) configurations across multiple related projects.

## Installation

Install globally to make the command available system-wide:

```bash
cd uv-deps-switcher
uv tool install .
```

For editable/development installation:

```bash
uv tool install -e .
```

After installation, the `uv-deps-switcher` command will be available globally from any directory.

## Configuration

Create a configuration file (`.uv-deps-switcher.toml` or `uv-deps-switcher.toml`) to define groups of repositories that should be switched together.

### Configuration File Location

The tool searches for config files in:
1. Current directory and parent directories (up to workspace root)
2. User home directory (`~/.uv-deps-switcher.toml`)

### Configuration Format

```toml
[groups.main]
description = "Main development group"
repos = ["PhoLogToLabStreamingLayer", "whisper-timestamped"]

[groups.all]
description = "All repos with templating"
repos = ["PhoLogToLabStreamingLayer", "whisper-timestamped", "PhoPyLSLhelper"]
```

Optional: `default_github_username` — when a missing dependency has no `git` URL in the release template, the tool resolves a GitHub username via the following priority chain:
1. `default_github_username` in this config file (explicit override — highest priority)
2. The active repo's `git remote origin` URL (e.g. `https://github.com/CommanderPho/repo.git` → `CommanderPho`)
3. `git config --global github.user` (common GitHub CLI / git convention)
4. Environment variables: `GITHUB_USERNAME`, `GH_USER`, or `GITHUB_USER`

Set `default_github_username` to override all automatic detection (e.g. for a fixed fork or non-GitHub host).

### Project Requirements

Projects must have:
- A `templating/` directory containing:
  - `pyproject_template_dev.toml_fragment` - Dev mode template (local editable paths)
  - `pyproject_template_release.toml_fragment` - Release mode template (git URLs)
  - *(optional)* Any additional `pyproject_template_<name>.toml_fragment` files are automatically detected as **custom modes** named `<name>` (e.g. `pyproject_template_kdiba.toml_fragment` → mode `kdiba`).
- Add `templating/uv_deps_switcher/backups/` to your repo's `.gitignore` so pyproject.toml backups are not committed (the tool does this automatically on first run).

#### Custom Modes

Drop any extra `pyproject_template_<name>.toml_fragment` file into a project's `templating/` folder and it becomes a custom mode:

```
templating/
  pyproject_template_dev.toml_fragment      ← built-in
  pyproject_template_release.toml_fragment  ← built-in
  pyproject_template_kdiba.toml_fragment    ← custom mode 'kdiba'
```

Custom modes behave like `dev` mode (local paths, clone-checking) if their template contains `path =` entries, or like `release` mode otherwise. Run `uv-deps-switcher list-modes` from inside a project to see which custom modes are available.

The templates should contain the `[tool.uv.sources]` section that will replace the corresponding section in each project's `pyproject.toml`.

### Environment Variable Support

Templates support the `ACTIVE_DEV_PATH_PREFIX` environment variable for machine-specific path configurations:

- **On machines where repos are siblings** (e.g., `ACTIVE_DEV/PhoOfflineEEGAnalysis`, `ACTIVE_DEV/PhoPyLSLhelper`):
  - Leave `ACTIVE_DEV_PATH_PREFIX` unset or set to empty string
  - Paths will be: `../PhoPyLSLhelper`, `../PhoPyMNEHelper`, etc.

- **On machines where repos are in an ACTIVE_DEV subfolder**:
  - Set `ACTIVE_DEV_PATH_PREFIX=ACTIVE_DEV/`
  - Paths will be: `../ACTIVE_DEV/PhoPyLSLhelper`, `../ACTIVE_DEV/PhoPyMNEHelper`, etc.

In template files, use the placeholder `{ACTIVE_DEV_PATH_PREFIX}` (for plain TOML templates) or `{{ ACTIVE_DEV_PATH_PREFIX }}` (for Jinja2 templates):

```toml
phopylslhelper = { path = "../{ACTIVE_DEV_PATH_PREFIX}PhoPyLSLhelper", editable = true }
```

## Usage

### Switch a Group

Switch all repos in a defined group:

```bash
# Switch to dev mode (local editable paths)
uv-deps-switcher dev --group main

# Switch to release mode (git URLs)
uv-deps-switcher release --group main
```

### Switch All Repos

Switch all detected repos (ignores groups):

```bash
uv-deps-switcher dev --all
```

### Switch a Single Repo

Switch a single repo by name:

```bash
uv-deps-switcher dev --repo PhoLogToLabStreamingLayer
```

### Switch Current Project (Local Mode)

When inside a valid project folder (containing the templating files), you can switch just that project without any flags:

```bash
cd /path/to/my-project
uv-deps-switcher dev      # Switch current project to dev mode
uv-deps-switcher release  # Switch current project to release mode
```

This is useful for quickly switching a single project without needing to specify groups or repo names.

### Custom Modes

If a project has additional template files such as `templating/pyproject_template_kdiba.toml_fragment`, they are automatically available as custom modes:

```bash
cd /path/to/my-project
uv-deps-switcher kdiba        # Apply custom 'kdiba' template
uv-deps-switcher list-modes   # Show all built-in and custom modes for this project
```

Custom modes work with all the same flags (`--group`, `--all`, `--repo`, `--dry-run`, etc.). If the custom template contains `path =` entries the tool will perform the same missing-dependency clone-check as `dev` mode.

### Deploy Templates to Current Project

Generate template fragments for the current project based on its existing `[tool.uv.sources]` and `[project.dependencies]`:

```bash
cd /path/to/my-project
uv-deps-switcher deploy-templates

# Dry run to preview what would be created
uv-deps-switcher deploy-templates --dry-run
```

This command:
1. Reads the current `[tool.uv.sources]` section from `pyproject.toml`
2. Filters sources to only include dependencies listed in `[project.dependencies]`
3. Generates dev templates (with local editable paths)
4. Generates release templates (with git URLs inferred from local repos)
5. Writes both templates to the `templating/` directory

### Auto-Clone Missing Dependencies

When switching to dev mode, if any local dependency paths don't exist, the tool will offer to clone them from GitHub. Clone URLs come from the release template when present; for dependencies with no `git` URL in the release template, the tool builds a fallback URL (`https://github.com/<username>/<repo>.git`, where `<repo>` is the last path component of the dev path) using a username resolved from the following priority chain:

1. `default_github_username` in `.uv-deps-switcher.toml` (explicit override)
2. The active repo's `git remote origin` URL (e.g. `https://github.com/CommanderPho/emotiv-lsl.git` → `CommanderPho`)
3. `git config --global github.user` (common GitHub CLI / git convention — set via `git config --global github.user YourUsername`)
4. Environment variables: `GITHUB_USERNAME`, `GH_USER`, or `GITHUB_USER`

```
$ uv-deps-switcher dev
Processing my-project...
  Missing local dependencies:
    - phopylslhelper -> ../PhoPyLSLhelper (not found)
    - neuropy -> ../NeuroPy (not found)
  
  Clone 2 missing repo(s) from GitHub? [y/N]: y
    Cloning https://github.com/CommanderPho/phopylslhelper.git...
    Cloned to ../PhoPyLSLhelper
    Cloning https://github.com/CommanderPho/NeuroPy.git...
    Cloned to ../NeuroPy
  Updated my-project to dev mode
```

Use `--no-clone` to skip this prompt and handle missing dependencies manually.

### Additional Options

```bash
# Skip confirmation prompt
uv-deps-switcher dev --group main --yes

# Specify workspace root explicitly
uv-deps-switcher dev --group main --workspace-root /path/to/workspace

# Dry run (show what would be changed without making changes)
uv-deps-switcher dev --group main --dry-run

# Skip auto-clone prompts for missing dependencies
uv-deps-switcher dev --no-clone

# List available groups
uv-deps-switcher list-groups
```

## How It Works

1. **Workspace Detection**: The tool automatically detects the workspace root by looking for:
   - `.code-workspace` files
   - `.vscode` folders
   - `ACTIVE_DEV` directory name
   - Or use `--workspace-root` to specify explicitly

2. **Project Discovery**: Scans the workspace for projects containing:
   - `templating/pyproject_template_dev.toml_fragment`
   - `templating/pyproject_template_release.toml_fragment`

3. **Template Application**: Replaces the `[tool.uv.sources]` section in each project's `pyproject.toml` with the content from the appropriate template file.

## Example Template Files

### `templating/pyproject_template_dev.toml_fragment`
```toml
[tool.uv.sources]
lab-recorder-python = { path = "../lab-recorder-python", editable = true }
whisper-timestamped = { path = "../whisper-timestamped", editable = true }
phopylslhelper = { path = "../PhoPyLSLhelper", editable = true }
```

### `templating/pyproject_template_release.toml_fragment`
```toml
[tool.uv.sources]
lab-recorder-python = { git = "https://github.com/CommanderPho/lab-recorder-python.git"}
whisper-timestamped = { git = "https://github.com/CommanderPho/whisper-timestamped.git"} 
phopylslhelper = { git = "https://github.com/CommanderPho/phopylslhelper.git" }
```

## Requirements

- Python 3.10+
- `tomli` (for Python < 3.11) or `tomllib` (built-in for Python 3.11+)
- `jinja2` (for template rendering)

## License

MIT

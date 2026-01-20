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

After installation, the `switch-uv-deps` command will be available globally from any directory.

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

### Project Requirements

Projects must have:
- A `templating/` directory containing:
  - `pyproject_template_dev.toml_fragment` - Dev mode template (local editable paths)
  - `pyproject_template_release.toml_fragment` - Release mode template (git URLs)

The templates should contain the `[tool.uv.sources]` section that will replace the corresponding section in each project's `pyproject.toml`.

## Usage

### Switch a Group

Switch all repos in a defined group:

```bash
# Switch to dev mode (local editable paths)
switch-uv-deps dev --group main

# Switch to release mode (git URLs)
switch-uv-deps release --group main
```

### Switch All Repos

Switch all detected repos (ignores groups):

```bash
switch-uv-deps dev --all
```

### Switch a Single Repo

Switch a single repo by name:

```bash
switch-uv-deps dev --repo PhoLogToLabStreamingLayer
```

### Additional Options

```bash
# Skip confirmation prompt
switch-uv-deps dev --group main --yes

# Specify workspace root explicitly
switch-uv-deps dev --group main --workspace-root /path/to/workspace

# Dry run (show what would be changed without making changes)
switch-uv-deps dev --group main --dry-run

# List available groups
switch-uv-deps list-groups
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

## License

MIT

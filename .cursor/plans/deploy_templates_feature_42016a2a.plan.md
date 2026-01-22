---
name: Deploy Templates Feature
overview: Add a `deploy-templates` command that generates template fragments from the current project's local dependencies and deploys them to the current project, filtering to only include dependencies that exist in the project's dependencies list.
todos:
  - id: move_templates
    content: Move templated_project_root_template to templates/ folder at project root
    status: completed
  - id: read_dependencies
    content: Add function to read project dependencies from pyproject.toml
    status: completed
  - id: read_sources
    content: Add function to read current [tool.uv.sources] from pyproject.toml
    status: completed
  - id: generate_dev_template
    content: Add function to generate dev template from sources dict
    status: completed
  - id: generate_release_template
    content: Add function to generate release template by converting paths to git URLs
    status: completed
  - id: filter_template
    content: Add function to filter template content by target dependencies
    status: completed
  - id: git_url_inference
    content: Implement logic to infer git URLs from local repository paths
    status: completed
  - id: deploy_command
    content: Add deploy-templates CLI command and main deployment function
    status: completed
  - id: path_calculation
    content: Implement relative path calculation for dev templates
    status: completed
isProject: false
---

# Deploy Templates Feature

## Overview

Add functionality to deploy template fragments to the current project based on its local dependencies. The templates will be generated from the current project's `[tool.uv.sources]` configuration and filtered to only include dependencies that exist in the project's `[project.dependencies]`.

## Implementation Plan

### 1. Move Template Structure

Move `src/resources/templated_project_root_template/` to `templates/` at the project root:

- Move `templating/pyproject_template_dev.toml_fragment` → `templates/pyproject_template_dev.toml_fragment`
- Move `templating/pyproject_template_release.toml_fragment` → `templates/pyproject_template_release.toml_fragment`
- Move `uv-deps-switcher.toml` → `templates/uv-deps-switcher.toml` (if needed as reference)

### 2. Add Dependency Reading Functions

In [`src/uv_deps_switcher/main.py`](src/uv_deps_switcher/main.py), add functions to:

- `read_project_dependencies(pyproject_path: Path) -> set[str]`: Read all dependency names from `[project.dependencies]` and `[tool.uv.sources]` in a pyproject.toml file. Extract package names from dependency strings (e.g., "package>=1.0" → "package").
- `read_current_sources(pyproject_path: Path) -> dict`: Read the current `[tool.uv.sources]` section from a pyproject.toml file and return as a dictionary.

### 3. Add Template Generation Functions

Add functions to generate templates from current sources:

- `generate_dev_template(sources: dict, project_path: Path) -> str`: Generate dev template fragment from sources dict, keeping paths relative to the project location.
- `generate_release_template(sources: dict) -> str`: Generate release template fragment by converting local paths to git URLs. This will need to infer git URLs from local paths (e.g., by checking if the path points to a git repo and reading its remote URL, or using a mapping).

### 4. Add Template Filtering

- `filter_template_by_dependencies(template_content: str, project_dependencies: set[str]) -> str`: Filter a template fragment to only include entries whose keys match dependencies in the project. Parse the template, filter the sources dict, and regenerate the TOML fragment.

### 5. Add Deploy Command

Add a new `deploy-templates` subcommand to the CLI:

- `deploy_templates(project_path: Path, dry_run: bool = False) -> bool`: Main deployment function that:

  1. Reads current project's `[tool.uv.sources]` from `project_path/pyproject.toml`
  2. Reads current project's dependencies from `[project.dependencies]`
  3. Generates dev and release templates from current sources
  4. Filters both templates to only include dependencies that exist in the project
  5. Creates `templating/` directory in project if it doesn't exist
  6. Writes filtered templates to project's `templating/` folder

- Update `main()` function to handle `deploy-templates` command with arguments:
  - No required arguments - works on current directory
  - `--dry-run`: Show what would be deployed without making changes
  - `--yes`: Skip confirmation

### 6. Git URL Inference

For generating release templates, implement logic to convert local paths to git URLs:

- Check if the local path is a git repository
- Read the remote URL (prefer "origin")
- If not a git repo or no remote found, skip that dependency in the release template (or log a warning)

### 7. Path Relative Calculation

When generating dev templates:

- Keep paths as they are in the current `[tool.uv.sources]` (they should already be relative to the project)
- Ensure paths remain valid relative to the project root

## File Changes

- [`src/uv_deps_switcher/main.py`](src/uv_deps_switcher/main.py): Add deploy functionality, dependency reading, template generation, and filtering functions
- Move template files from `src/resources/templated_project_root_template/` to `templates/` at project root
- Update `.gitignore` if needed to exclude generated templates

## Usage Example

```bash
# Deploy templates to current project (must be run from project directory)
cd /path/to/my-project
uv-deps-switcher deploy-templates

# Deploy with dry-run to see what would be created
uv-deps-switcher deploy-templates --dry-run
```

## Considerations

- Git URL inference may require the `git` command or `GitPython` library. Prefer using subprocess to call `git` command to avoid adding dependencies.
- Path calculations need to handle both absolute and relative paths correctly.
- Template filtering should preserve formatting and comments where possible.
- If a dependency exists in `[tool.uv.sources]` but not in `[project.dependencies]`, it should be excluded from the deployed template.
- The command should validate that it's being run from a project directory with a `pyproject.toml` file.
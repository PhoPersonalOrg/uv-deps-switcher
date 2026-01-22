---
name: Clone Missing Dependencies
overview: Add functionality to detect missing local dependency paths when switching to dev mode, and offer to clone them from GitHub to the specified relative directory.
todos:
  - id: extract_paths
    content: Add extract_dev_paths() and extract_git_urls() functions to parse templates
    status: completed
  - id: find_missing
    content: Add find_missing_dependencies() to check which local paths don't exist
    status: completed
  - id: clone_dep
    content: Add clone_dependency() function to clone a git repo to target path
    status: completed
  - id: check_clone_flow
    content: Add check_and_clone_missing_deps() to orchestrate the prompt and clone flow
    status: completed
  - id: integrate_switch
    content: Modify switch_repos() to call clone check when mode is dev
    status: completed
  - id: add_no_clone_flag
    content: Add --no-clone CLI flag to skip clone prompts
    status: completed
isProject: false
---

# Clone Missing Dependencies on Dev Switch

## Overview

When switching to `dev` mode, the tool will check if the local paths specified in the dev template actually exist. If any are missing, it will prompt the user to clone them from the corresponding git URLs in the release template.

## Implementation

### 1. Add Path/URL Extraction Functions

Add to [`src/uv_deps_switcher/main.py`](src/uv_deps_switcher/main.py):

- `extract_dev_paths(template_content: str) -> Dict[str, str]`: Parse dev template and extract mapping of `{dep_name: local_path}` (e.g., `{"phopylslhelper": "../PhoPyLSLhelper"}`)

- `extract_git_urls(template_content: str) -> Dict[str, str]`: Parse release template and extract mapping of `{dep_name: git_url}` (e.g., `{"phopylslhelper": "https://github.com/CommanderPho/phopylslhelper.git"}`)

### 2. Add Missing Path Detection

- `find_missing_dependencies(project_path: Path, dev_paths: Dict[str, str]) -> List[Tuple[str, str]]`: Check which paths don't exist relative to project, return list of `(dep_name, missing_path)`

### 3. Add Clone Function

- `clone_dependency(git_url: str, target_path: Path) -> bool`: Clone a git repository to the specified path using `git clone`

### 4. Add Prompt and Clone Flow

- `check_and_clone_missing_deps(project_path: Path, dev_template: str, release_template: str, dry_run: bool, auto_yes: bool) -> bool`: Main function that:

        1. Extracts dev paths and git URLs from templates
        2. Finds missing paths
        3. If any missing, shows list and asks user to confirm cloning
        4. Clones each missing dependency
        5. Returns True if all clones successful or no clones needed

### 5. Integrate into Switch Flow

Modify `switch_repos()` in [`src/uv_deps_switcher/main.py`](src/uv_deps_switcher/main.py):

- Before updating pyproject.toml, if mode is "dev":
        - Read both dev and release templates
        - Call `check_and_clone_missing_deps()`
        - If user declines or clone fails, skip this repo

### 6. Add CLI Flag

Add `--no-clone` flag to skip the clone prompt entirely (for users who want to handle missing deps manually).

## User Experience Flow

```
$ uv-deps-switcher dev
Switching 1 repo(s) to dev mode:
  - my-project

Proceed? [y/N]: y

Processing my-project...
  Missing local dependencies:
    - phopylslhelper -> ../PhoPyLSLhelper (not found)
    - neuropy -> ../NeuroPy (not found)
  
  Clone from GitHub? [y/N]: y
  Cloning phopylslhelper from https://github.com/CommanderPho/phopylslhelper.git...
    Cloned to ../PhoPyLSLhelper
  Cloning neuropy from https://github.com/CommanderPho/NeuroPy.git...
    Cloned to ../NeuroPy
  Updated my-project to dev mode
```

## File Changes

- [`src/uv_deps_switcher/main.py`](src/uv_deps_switcher/main.py): Add extraction functions, clone logic, and integrate into switch flow
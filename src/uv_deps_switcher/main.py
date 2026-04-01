"""Main CLI entry point for UV dependency switcher."""

import argparse
import os
import re
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from jinja2 import Environment, BaseLoader, TemplateNotFound

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from .config import find_config_file, get_default_github_username, get_github_username_from_env, get_github_username_from_git_config, get_group_repos, list_groups, load_config


class PackageTemplateLoader(BaseLoader):
    """Jinja2 template loader that loads from package resources."""
    
    def __init__(self, package: str):
        self.package = package
    
    def get_source(self, environment, template):
        try:
            # Python 3.9+ way to read package resources
            template_path = resources.files(self.package).joinpath(template)
            source = template_path.read_text(encoding="utf-8")
            return source, str(template_path), lambda: True
        except (FileNotFoundError, TypeError):
            raise TemplateNotFound(template)


def get_jinja_env() -> Environment:
    """Get Jinja2 environment configured to load templates from package."""
    loader = PackageTemplateLoader("uv_deps_switcher.templates")
    return Environment(loader=loader, keep_trailing_newline=True)


def parse_template_sources(template_content: str) -> dict:
    """Parse template content and extract the [tool.uv.sources] dictionary."""
    try:
        parsed = tomllib.loads(template_content)
        return parsed.get("tool", {}).get("uv", {}).get("sources", {})
    except Exception:
        return {}


def extract_dev_paths(template_content: str) -> Dict[str, str]:
    """Extract local paths from dev template. Returns {dep_name: local_path}."""
    sources = parse_template_sources(template_content)
    paths = {}
    for dep_name, config in sources.items():
        if isinstance(config, dict) and "path" in config:
            paths[dep_name] = config["path"]
    return paths


def extract_git_urls(template_content: str) -> Dict[str, str]:
    """Extract git URLs from release template. Returns {dep_name: git_url}."""
    sources = parse_template_sources(template_content)
    urls = {}
    for dep_name, config in sources.items():
        if isinstance(config, dict) and "git" in config:
            urls[dep_name] = config["git"]
    return urls


def find_missing_dependencies(project_path: Path, dev_paths: Dict[str, str]) -> List[Tuple[str, str]]:
    """Check which local dependency paths don't exist. Returns list of (dep_name, missing_path)."""
    missing = []
    for dep_name, rel_path in dev_paths.items():
        # Resolve the path relative to the project
        abs_path = (project_path / rel_path).resolve()
        if not abs_path.exists():
            missing.append((dep_name, rel_path))
    return missing


def clone_dependency(git_url: str, target_path: Path, dry_run: bool = False) -> bool:
    """Clone a git repository to the specified path."""
    if dry_run:
        print(f"    [DRY RUN] Would clone {git_url} to {target_path}")
        return True
    
    if target_path.exists():
        print(f"    Warning: {target_path} already exists, skipping clone", file=sys.stderr)
        return True
    
    try:
        print(f"    Cloning {git_url}...")
        result = subprocess.run(["git", "clone", git_url, str(target_path)], capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"    Cloned to {target_path}")
            return True
        else:
            print(f"    Error cloning: {result.stderr}", file=sys.stderr)
            return False
    except subprocess.TimeoutExpired:
        print(f"    Error: Clone timed out after 5 minutes", file=sys.stderr)
        return False
    except Exception as e:
        print(f"    Error cloning: {e}", file=sys.stderr)
        return False


def check_and_clone_missing_deps(project_path: Path, dev_template: str, release_template: str, dry_run: bool = False, auto_yes: bool = False, no_clone: bool = False, default_github_username: Optional[str] = None) -> bool:
    """Check for missing dependencies and offer to clone them. Returns True if ready to proceed."""
    if no_clone:
        return True
    
    # Extract paths and URLs from templates
    dev_paths = extract_dev_paths(dev_template)
    git_urls = extract_git_urls(release_template)
    
    effective_username = resolve_github_username(project_path, config_override=default_github_username)
    
    # Find missing paths
    missing = find_missing_dependencies(project_path, dev_paths)
    
    if not missing:
        return True
    
    # Show missing dependencies
    print(f"  Missing local dependencies:")
    cloneable = []
    for dep_name, rel_path in missing:
        abs_path = (project_path / rel_path).resolve()
        if dep_name in git_urls:
            print(f"    - {dep_name} -> {rel_path} (not found)")
            cloneable.append((dep_name, rel_path, git_urls[dep_name]))
        elif effective_username:
            repo_name = Path(rel_path).name
            fallback_url = f"https://github.com/{effective_username}/{repo_name}.git"
            print(f"    - {dep_name} -> {rel_path} (not found, inferred from origin)")
            cloneable.append((dep_name, rel_path, fallback_url))
        else:
            print(f"    - {dep_name} -> {rel_path} (not found, no git URL available)")
    
    if not cloneable:
        print(f"  Warning: No git URLs available for missing dependencies", file=sys.stderr)
        return True  # Continue anyway, uv will fail later if deps are missing
    
    # Ask user if they want to clone
    if not dry_run and not auto_yes:
        response = input(f"\n  Clone {len(cloneable)} missing repo(s) from GitHub? [y/N]: ")
        if response.lower() not in ["y", "yes"]:
            print("  Skipping clone, continuing with switch...")
            return True
    
    # Clone each missing dependency
    all_success = True
    for dep_name, rel_path, git_url in cloneable:
        target_path = (project_path / rel_path).resolve()
        if not clone_dependency(git_url, target_path, dry_run=dry_run):
            all_success = False
    
    return all_success


def extract_source_key(line: str) -> Optional[str]:
    """Extract the key name from a TOML source line (e.g., 'some-dep = {...}' -> 'some-dep')."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("["):
        return None
    if "=" in stripped:
        key = stripped.split("=", 1)[0].strip()
        # Handle quoted keys
        if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
            key = key[1:-1]
        return key if key else None
    return None


def find_workspace_root(start_path: Path) -> Optional[Path]:
    """Find workspace root by looking for .code-workspace, .vscode, or ACTIVE_DEV."""
    current = start_path.resolve()
    
    # Check for .code-workspace or .vscode folder
    while current != current.parent:
        if (current / ".code-workspace").exists() or (current / ".vscode").exists():
            return current
        # Check if we're in ACTIVE_DEV
        if current.name == "ACTIVE_DEV":
            return current
        current = current.parent
    
    return None


def is_valid_project(project_path: Path) -> bool:
    """Check if a directory is a valid project with templating."""
    templating_dir = project_path / "templating"
    dev_template = templating_dir / "pyproject_template_dev.toml_fragment"
    release_template = templating_dir / "pyproject_template_release.toml_fragment"
    return dev_template.exists() and release_template.exists()


def find_projects_with_templating(workspace_root: Path) -> List[Path]:
    """Find all projects that have templating folders with both dev and release templates."""
    projects = []
    
    if not workspace_root.exists():
        return projects
    
    for item in workspace_root.iterdir():
        if not item.is_dir():
            continue
        
        templating_dir = item / "templating"
        if not templating_dir.exists() or not templating_dir.is_dir():
            continue
        
        dev_template = templating_dir / "pyproject_template_dev.toml_fragment"
        release_template = templating_dir / "pyproject_template_release.toml_fragment"
        
        if dev_template.exists() and release_template.exists():
            projects.append(item)
    
    return projects


def read_template(project_path: Path, mode: str) -> Optional[str]:
    """Read template file for a project and process environment variable placeholders."""
    template_file = project_path / "templating" / f"pyproject_template_{mode}.toml_fragment"
    
    if not template_file.exists():
        return None
    
    try:
        template_content = template_file.read_text(encoding="utf-8")
        # Process environment variable placeholders
        # Get ACTIVE_DEV_PATH_PREFIX from environment, default to empty string
        path_prefix = os.getenv("ACTIVE_DEV_PATH_PREFIX", "")
        # Substitute placeholder in template content
        processed_content = template_content.replace("{ACTIVE_DEV_PATH_PREFIX}", path_prefix)
        return processed_content
    except Exception as e:
        print(f"Error reading template {template_file}: {e}", file=sys.stderr)
        return None


def update_pyproject_sources(pyproject_path: Path, template_content: str, dry_run: bool = False) -> bool:
    """Update [tool.uv.sources] section in pyproject.toml, merging template items with existing entries."""
    if not pyproject_path.exists():
        print(f"Error: {pyproject_path} does not exist", file=sys.stderr)
        return False
    
    if dry_run:
        print(f"  [DRY RUN] Would update {pyproject_path}")
        return True
    
    try:
        # Parse template to get keys and build a mapping of key -> line content
        template_sources = parse_template_sources(template_content)
        template_keys = set(template_sources.keys())
        
        # Build template lines mapping (key -> full line text)
        template_lines_map = {}
        for tline in template_content.strip().split("\n"):
            tkey = extract_source_key(tline)
            if tkey and tkey in template_keys:
                template_lines_map[tkey] = tline
        
        # Track which template keys have been used
        used_template_keys = set()
        
        # Read current file
        content = pyproject_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        new_lines = []
        in_sources_section = False
        section_found = False
        
        # Process lines to find and merge [tool.uv.sources] section
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Detect start of [tool.uv.sources] section
            if stripped == "[tool.uv.sources]":
                section_found = True
                in_sources_section = True
                new_lines.append("[tool.uv.sources]")
                i += 1
                
                # Process existing section lines and merge with template
                while i < len(lines):
                    next_line = lines[i]
                    next_stripped = next_line.strip()
                    
                    # Stop at next section (starts with [)
                    if next_stripped.startswith("[") and not next_stripped.startswith("[tool.uv.sources"):
                        in_sources_section = False
                        # Add any unused template keys before leaving section
                        for tkey in template_keys - used_template_keys:
                            if tkey in template_lines_map:
                                new_lines.append(template_lines_map[tkey])
                        # Add blank line before next section if needed
                        if new_lines and new_lines[-1].strip():
                            new_lines.append("")
                        new_lines.append(next_line)
                        i += 1
                        break
                    
                    # Check if this line has a key we should replace
                    line_key = extract_source_key(next_line)
                    if line_key and line_key in template_keys:
                        # Replace with template version
                        if line_key in template_lines_map:
                            new_lines.append(template_lines_map[line_key])
                        used_template_keys.add(line_key)
                    elif next_stripped:
                        # Keep existing line (not in template, or blank/comment)
                        new_lines.append(next_line)
                    else:
                        # Preserve blank lines
                        new_lines.append(next_line)
                    
                    i += 1
                
                # Handle case where section goes to end of file
                if in_sources_section:
                    in_sources_section = False
                    # Add any unused template keys
                    for tkey in template_keys - used_template_keys:
                        if tkey in template_lines_map:
                            new_lines.append(template_lines_map[tkey])
                continue
            
            # Regular line - add it if we're not in sources section
            if not in_sources_section:
                new_lines.append(line)
            
            i += 1
        
        # If section wasn't found, append it at the end
        if not section_found:
            if new_lines and new_lines[-1].strip():
                new_lines.append("")
            new_lines.append("[tool.uv.sources]")
            for tkey in template_keys:
                if tkey in template_lines_map:
                    new_lines.append(template_lines_map[tkey])
        
        # Save backup before writing changes
        backup_dir = pyproject_path.parent / "templating" / "uv_deps_switcher" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pyproject_path, backup_dir / "pyproject.toml.bak")
        
        # Write updated content
        updated_content = "\n".join(new_lines)
        if not updated_content.endswith("\n"):
            updated_content += "\n"
        pyproject_path.write_text(updated_content, encoding="utf-8")
        return True
        
    except Exception as e:
        print(f"Error updating {pyproject_path}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def extract_package_name(dep_string: str) -> str:
    """Extract package name from a dependency string (e.g., 'package>=1.0' -> 'package')."""
    # Remove extras like [extra1,extra2]
    dep_string = re.split(r'\[', dep_string)[0]
    # Remove version specifiers
    dep_string = re.split(r'[<>=!~;]', dep_string)[0]
    return dep_string.strip()


def read_project_dependencies(pyproject_path: Path) -> Set[str]:
    """Read all dependency names from [project.dependencies] in a pyproject.toml file."""
    if not pyproject_path.exists():
        return set()
    
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        
        deps = set()
        # Read from [project.dependencies]
        project_deps = data.get("project", {}).get("dependencies", [])
        for dep in project_deps:
            pkg_name = extract_package_name(dep)
            if pkg_name:
                deps.add(pkg_name)
        
        # Also read from [project.optional-dependencies] if present
        optional_deps = data.get("project", {}).get("optional-dependencies", {})
        for group_deps in optional_deps.values():
            for dep in group_deps:
                pkg_name = extract_package_name(dep)
                if pkg_name:
                    deps.add(pkg_name)
        
        return deps
    except Exception as e:
        print(f"Error reading dependencies from {pyproject_path}: {e}", file=sys.stderr)
        return set()


def read_current_sources(pyproject_path: Path) -> Dict[str, dict]:
    """Read the current [tool.uv.sources] section from a pyproject.toml file."""
    if not pyproject_path.exists():
        return {}
    
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        return data.get("tool", {}).get("uv", {}).get("sources", {})
    except Exception as e:
        print(f"Error reading sources from {pyproject_path}: {e}", file=sys.stderr)
        return {}


def get_git_remote_url(repo_path: Path) -> Optional[str]:
    """Get the git remote URL (origin) from a local repository path."""
    if not repo_path.exists() or not repo_path.is_dir():
        return None
    
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return None
    
    try:
        result = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo_path, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            url = result.stdout.strip()
            # Convert SSH URLs to HTTPS if needed
            if url.startswith("git@"):
                # git@github.com:user/repo.git -> https://github.com/user/repo.git
                url = re.sub(r'^git@([^:]+):', r'https://\1/', url)
            return url
        return None
    except Exception:
        return None


def get_github_username_from_origin(repo_path: Path) -> Optional[str]:
    """Extract GitHub username from the repo's origin URL (e.g. https://github.com/CommanderPho/emotiv-lsl.git -> CommanderPho)."""
    url = get_git_remote_url(repo_path)
    if not url or "github.com" not in url:
        return None
    match = re.search(r"github\.com[/:]([^/]+)", url)
    return match.group(1) if match else None


def resolve_github_username(project_path: Path, config_override: Optional[str] = None) -> Optional[str]:
    """Resolve the GitHub username to use for cloning missing dependencies.

    Priority chain (highest to lowest):
    1. config_override — explicit value from .uv-deps-switcher.toml
    2. git remote origin URL of project_path — e.g. https://github.com/CommanderPho/repo.git → CommanderPho
    3. git config --global github.user — common GitHub CLI / git convention
    4. Environment variables: GITHUB_USERNAME, GH_USER, GITHUB_USER
    """
    if config_override and config_override.strip():
        return config_override.strip()
    origin_username = get_github_username_from_origin(project_path)
    if origin_username:
        return origin_username
    git_config_username = get_github_username_from_git_config()
    if git_config_username:
        return git_config_username
    return get_github_username_from_env()


def filter_sources_by_dependencies(sources: Dict[str, dict], dependencies: Set[str]) -> Dict[str, dict]:
    """Filter sources dict to only include entries that match project dependencies."""
    filtered = {}
    for key, value in sources.items():
        if key in dependencies:
            filtered[key] = value
    return filtered


def render_template(template_name: str, include_deps: Set[str]) -> str:
    """Render a Jinja2 template with the given dependencies to include."""
    env = get_jinja_env()
    template = env.get_template(template_name)
    # Get ACTIVE_DEV_PATH_PREFIX from environment, default to empty string
    path_prefix = os.getenv("ACTIVE_DEV_PATH_PREFIX", "")
    return template.render(include_deps=include_deps, ACTIVE_DEV_PATH_PREFIX=path_prefix)


def generate_dev_template(include_deps: Set[str]) -> str:
    """Generate dev template fragment using Jinja2 template."""
    return render_template("pyproject_template_dev.toml_fragment.j2", include_deps)


def generate_release_template(include_deps: Set[str]) -> str:
    """Generate release template fragment using Jinja2 template."""
    return render_template("pyproject_template_release.toml_fragment.j2", include_deps)


def generate_workspace_template(include_deps: Set[str]) -> str:
    """Generate workspace template fragment using Jinja2 template."""
    return render_template("pyproject_template_workspace.toml_fragment.j2", include_deps)


def generate_workspace_fragment_from_templates(project_path: Path) -> Optional[str]:
    """Generate a workspace fragment from existing dev and release fragments.

    For each dep that has a local path in the dev fragment, emits `dep = { workspace = true }`.
    All other entries (git-pinned tools/libs) are preserved unchanged from the release fragment.
    Returns the fragment string, or None if dev/release fragments are missing or empty.
    """
    dev_content = read_template(project_path, "dev")
    release_content = read_template(project_path, "release")
    if not dev_content or not release_content:
        return None

    workspace_keys = set(extract_dev_paths(dev_content).keys())
    if not workspace_keys:
        return None

    release_lines = release_content.strip().split("\n")
    emitted_workspace_keys: Set[str] = set()
    output_lines: List[str] = []

    for line in release_lines:
        key = extract_source_key(line)
        if key and key in workspace_keys:
            output_lines.append(f"{key} = {{ workspace = true }}")
            emitted_workspace_keys.add(key)
        else:
            output_lines.append(line)

    for key in workspace_keys - emitted_workspace_keys:
        output_lines.append(f"{key} = {{ workspace = true }}")

    return "\n".join(output_lines) + "\n"


def deploy_templates(project_path: Path, dry_run: bool = False) -> bool:
    """Deploy template fragments to a project based on its current dependencies and sources."""
    pyproject_path = project_path / "pyproject.toml"
    
    if not pyproject_path.exists():
        print(f"Error: {pyproject_path} does not exist", file=sys.stderr)
        return False
    
    # Read current sources and dependencies
    sources = read_current_sources(pyproject_path)
    dependencies = read_project_dependencies(pyproject_path)
    
    # Determine which dependencies to include in templates
    # Use sources keys if available, otherwise use project dependencies
    if sources:
        # Filter to only include source keys that are also in dependencies
        include_deps = set(sources.keys())
        if dependencies:
            include_deps = include_deps & dependencies
    elif dependencies:
        include_deps = dependencies
    else:
        print("Error: No [tool.uv.sources] or [project.dependencies] found in pyproject.toml", file=sys.stderr)
        return False
    
    if not include_deps:
        print("Warning: No matching dependencies found. Using all sources.", file=sys.stderr)
        include_deps = set(sources.keys()) if sources else dependencies
    
    # Generate templates using Jinja2
    dev_template = generate_dev_template(include_deps)
    release_template = generate_release_template(include_deps)
    workspace_template = generate_workspace_template(include_deps)

    # Show what will be created
    print(f"Deploying templates to {project_path.name}...")
    print(f"  Dependencies to include: {', '.join(sorted(include_deps))}")

    if dry_run:
        print("\n[DRY RUN] Would create:")
        print(f"  templating/pyproject_template_dev.toml_fragment")
        print(f"  templating/pyproject_template_release.toml_fragment")
        print(f"  templating/pyproject_template_workspace.toml_fragment")
        print("\nDev template content:")
        print(dev_template)
        print("Release template content:")
        print(release_template)
        print("Workspace template content:")
        print(workspace_template)
        return True

    # Create templating directory if it doesn't exist
    templating_dir = project_path / "templating"
    templating_dir.mkdir(parents=True, exist_ok=True)

    # Write templates
    dev_path = templating_dir / "pyproject_template_dev.toml_fragment"
    release_path = templating_dir / "pyproject_template_release.toml_fragment"
    workspace_path = templating_dir / "pyproject_template_workspace.toml_fragment"

    try:
        dev_path.write_text(dev_template, encoding="utf-8")
        release_path.write_text(release_template, encoding="utf-8")
        workspace_path.write_text(workspace_template, encoding="utf-8")
        print(f"  Created {dev_path}")
        print(f"  Created {release_path}")
        print(f"  Created {workspace_path}")
        return True
    except Exception as e:
        print(f"Error writing templates: {e}", file=sys.stderr)
        return False


def ensure_workspace_fragment(repo_path: Path, dry_run: bool = False) -> Optional[str]:
    """Ensure a workspace fragment exists for repo_path, generating it from dev+release if needed.

    Returns the fragment content string if available (either pre-existing or freshly generated),
    or None if it could not be produced.
    """
    workspace_file = repo_path / "templating" / "pyproject_template_workspace.toml_fragment"
    if workspace_file.exists():
        return read_template(repo_path, "workspace")

    content = generate_workspace_fragment_from_templates(repo_path)
    if content is None:
        return None

    if dry_run:
        print(f"  [DRY RUN] Would generate workspace fragment at {workspace_file}")
        return content

    templating_dir = repo_path / "templating"
    templating_dir.mkdir(parents=True, exist_ok=True)
    workspace_file.write_text(content, encoding="utf-8")
    print(f"  Generated workspace fragment: {workspace_file}")
    return content


def switch_repos(repos: List[Path], mode: str, dry_run: bool = False, auto_yes: bool = False, no_clone: bool = False) -> int:
    """Switch dependencies for a list of repos."""
    success_count = 0
    fail_count = 0

    for repo_path in repos:
        repo_name = repo_path.name
        print(f"Processing {repo_name}...")

        if mode == "workspace":
            template_content = ensure_workspace_fragment(repo_path, dry_run=dry_run)
        else:
            template_content = read_template(repo_path, mode)

        if template_content is None:
            print(f"  Error: Could not read template for {repo_name}", file=sys.stderr)
            fail_count += 1
            continue

        pyproject_path = repo_path / "pyproject.toml"
        if not pyproject_path.exists():
            print(f"  Warning: {pyproject_path} does not exist, skipping", file=sys.stderr)
            fail_count += 1
            continue

        # For dev mode, check for missing dependencies and offer to clone
        if mode == "dev":
            release_template = read_template(repo_path, "release")
            if release_template:
                default_username = get_default_github_username()
                check_and_clone_missing_deps(repo_path, template_content, release_template, dry_run=dry_run, auto_yes=auto_yes, no_clone=no_clone, default_github_username=default_username)
        
        if update_pyproject_sources(pyproject_path, template_content, dry_run=dry_run):
            if not dry_run:
                print(f"  Updated {repo_name} to {mode} mode")
            success_count += 1
        else:
            print(f"  Error: Failed to update {repo_name}", file=sys.stderr)
            fail_count += 1

    return fail_count


def main():
    """Main CLI entry point."""
    # Handle list-groups command separately
    if len(sys.argv) > 1 and sys.argv[1] == "list-groups":
        groups = load_config()
        list_groups(groups)
        return 0
    
    # Handle deploy-templates command separately
    if len(sys.argv) > 1 and sys.argv[1] == "deploy-templates":
        deploy_parser = argparse.ArgumentParser(prog="uv-deps-switcher deploy-templates", description="Deploy template fragments to current project based on its dependencies")
        deploy_parser.add_argument("--dry-run", action="store_true", help="Show what would be created without making changes")
        deploy_parser.add_argument("-y", "--yes", "--force", action="store_true", dest="yes", help="Skip confirmation prompts (auto-confirm all actions)")
        deploy_args = deploy_parser.parse_args(sys.argv[2:])
        
        cwd = Path.cwd()
        pyproject_path = cwd / "pyproject.toml"
        
        if not pyproject_path.exists():
            print("Error: No pyproject.toml found in current directory", file=sys.stderr)
            return 1
        
        if not deploy_args.dry_run and not deploy_args.yes:
            response = input(f"Deploy templates to {cwd.name}? [y/N]: ")
            if response.lower() not in ["y", "yes"]:
                print("Cancelled")
                return 0
        
        if deploy_templates(cwd, dry_run=deploy_args.dry_run):
            if not deploy_args.dry_run:
                print("\nSuccessfully deployed templates!")
            return 0
        return 1
    
    parser = argparse.ArgumentParser(
        description="Switch UV dependency sources between dev and release configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv-deps-switcher dev                              # Switch current project (if valid)
  uv-deps-switcher release                          # Switch current project to release mode
  uv-deps-switcher workspace                        # Switch current project to workspace mode (monorepo)
  uv-deps-switcher dev --group main                 # Switch all repos in a group
  uv-deps-switcher release --group main
  uv-deps-switcher workspace --all                  # Switch all repos to workspace mode
  uv-deps-switcher dev --all                        # Switch all detected repos
  uv-deps-switcher dev --repo PhoLogToLabStreamingLayer
  uv-deps-switcher list-groups
  uv-deps-switcher deploy-templates                 # Deploy templates to current project
        """
    )

    parser.add_argument(
        "mode",
        choices=["dev", "release", "workspace"],
        help="Mode to switch to: dev (local editable paths), release (git), or workspace (uv monorepo, { workspace = true })"
    )
    parser.add_argument(
        "--group",
        help="Switch all repos in a defined group"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Switch all detected repos (ignores groups)"
    )
    parser.add_argument(
        "--repo",
        help="Switch a single repo by name"
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        help="Explicit workspace root path"
    )
    parser.add_argument(
        "-y", "--yes", "--force",
        action="store_true",
        dest="yes",
        help="Skip confirmation prompts (auto-confirm all actions)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes"
    )
    parser.add_argument(
        "--no-clone",
        action="store_true",
        help="Skip prompts to clone missing dependencies (dev mode only)"
    )
    
    args = parser.parse_args()
    
    # Determine which repos to switch
    repos_to_switch = []
    
    # Check if running in local project mode (no flags, current dir is valid project)
    if not args.all and not args.group and not args.repo:
        cwd = Path.cwd()
        if is_valid_project(cwd):
            repos_to_switch = [cwd]
        else:
            print("Error: Must specify --group, --all, or --repo, or run from within a valid project folder", file=sys.stderr)
            return 1
    else:
        # Need workspace root for --all, --group, or --repo modes
        if args.workspace_root:
            workspace_root = Path(args.workspace_root).resolve()
        else:
            workspace_root = find_workspace_root(Path.cwd())
            if workspace_root is None:
                print("Error: Could not detect workspace root. Use --workspace-root to specify it.", file=sys.stderr)
                return 1
        
        # Find all projects with templating
        all_projects = find_projects_with_templating(workspace_root)
        
        if not all_projects:
            print(f"No projects with templating folders found in {workspace_root}", file=sys.stderr)
            return 1
        
        if args.all:
            repos_to_switch = all_projects
        elif args.group:
            groups = load_config()
            group_repos = get_group_repos(groups, args.group)
            if group_repos is None:
                print(f"Error: Group '{args.group}' not found in configuration", file=sys.stderr)
                print("Available groups:", file=sys.stderr)
                list_groups(groups)
                return 1
            
            # Match group repo names to project paths
            for project_path in all_projects:
                if project_path.name in group_repos:
                    repos_to_switch.append(project_path)
            
            # Check for missing repos
            found_repos = {p.name for p in repos_to_switch}
            missing_repos = set(group_repos) - found_repos
            if missing_repos:
                print(f"Warning: Some repos in group '{args.group}' were not found: {', '.join(missing_repos)}", file=sys.stderr)
        elif args.repo:
            for project_path in all_projects:
                if project_path.name == args.repo:
                    repos_to_switch.append(project_path)
                    break
            if not repos_to_switch:
                print(f"Error: Repo '{args.repo}' not found", file=sys.stderr)
                return 1
    
    if not repos_to_switch:
        print("No repos to switch", file=sys.stderr)
        return 1
    
    # Show what will be changed
    print(f"Switching {len(repos_to_switch)} repo(s) to {args.mode} mode:")
    for repo_path in repos_to_switch:
        print(f"  - {repo_path.name}")
    
    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")
    elif not args.yes:
        response = input("\nProceed? [y/N]: ")
        if response.lower() not in ["y", "yes"]:
            print("Cancelled")
            return 0
    
    # Perform the switch
    print()
    fail_count = switch_repos(repos_to_switch, args.mode, dry_run=args.dry_run, auto_yes=args.yes, no_clone=args.no_clone)
    
    if fail_count > 0:
        return 1
    
    if not args.dry_run:
        print(f"\nSuccessfully switched {len(repos_to_switch)} repo(s) to {args.mode} mode")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

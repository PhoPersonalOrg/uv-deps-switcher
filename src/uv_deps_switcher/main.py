"""Main CLI entry point for UV dependency switcher."""

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from .config import find_config_file, get_group_repos, list_groups, load_config


def parse_template_sources(template_content: str) -> dict:
    """Parse template content and extract the [tool.uv.sources] dictionary."""
    try:
        parsed = tomllib.loads(template_content)
        return parsed.get("tool", {}).get("uv", {}).get("sources", {})
    except Exception:
        return {}


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
    """Read template file for a project."""
    template_file = project_path / "templating" / f"pyproject_template_{mode}.toml_fragment"
    
    if not template_file.exists():
        return None
    
    try:
        return template_file.read_text(encoding="utf-8")
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


def switch_repos(repos: List[Path], mode: str, dry_run: bool = False) -> int:
    """Switch dependencies for a list of repos."""
    success_count = 0
    fail_count = 0
    
    for repo_path in repos:
        repo_name = repo_path.name
        print(f"Processing {repo_name}...")
        
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
    
    parser = argparse.ArgumentParser(
        description="Switch UV dependency sources between dev and release configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  switch-uv-deps dev --group main
  switch-uv-deps release --group main
  switch-uv-deps dev --all
  switch-uv-deps dev --repo PhoLogToLabStreamingLayer
  switch-uv-deps list-groups
        """
    )
    
    parser.add_argument(
        "mode",
        choices=["dev", "release"],
        help="Mode to switch to: dev (local editable) or release (git)"
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
        "--yes",
        action="store_true",
        help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes"
    )
    
    args = parser.parse_args()
    
    # Determine workspace root
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
    
    # Determine which repos to switch
    repos_to_switch = []
    
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
    else:
        print("Error: Must specify --group, --all, or --repo", file=sys.stderr)
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
    fail_count = switch_repos(repos_to_switch, args.mode, dry_run=args.dry_run)
    
    if fail_count > 0:
        return 1
    
    if not args.dry_run:
        print(f"\nSuccessfully switched {len(repos_to_switch)} repo(s) to {args.mode} mode")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Main CLI entry point for UV dependency switcher."""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from .config import find_config_file, get_group_repos, list_groups, load_config


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
    """Update [tool.uv.sources] section in pyproject.toml."""
    if not pyproject_path.exists():
        print(f"Error: {pyproject_path} does not exist", file=sys.stderr)
        return False
    
    if dry_run:
        print(f"  [DRY RUN] Would update {pyproject_path}")
        return True
    
    try:
        # Read current file
        content = pyproject_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        new_lines = []
        in_sources_section = False
        section_found = False
        
        # Process lines to find and replace [tool.uv.sources] section
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Detect start of [tool.uv.sources] section
            if stripped == "[tool.uv.sources]":
                section_found = True
                in_sources_section = True
                # Add the section header
                new_lines.append("[tool.uv.sources]")
                # Add template content (skip the header if present)
                template_lines = template_content.strip().split("\n")
                for template_line in template_lines:
                    template_stripped = template_line.strip()
                    # Skip if it's the section header
                    if template_stripped == "[tool.uv.sources]":
                        continue
                    new_lines.append(template_line)
                
                # Skip current line and continue to find end of section
                i += 1
                # Skip all lines until we hit the next section or end of file
                while i < len(lines):
                    next_line = lines[i]
                    next_stripped = next_line.strip()
                    # Stop at next section (starts with [)
                    if next_stripped.startswith("[") and not next_stripped.startswith("[tool.uv.sources"):
                        in_sources_section = False
                        # Add blank line before next section
                        if new_lines and new_lines[-1].strip():
                            new_lines.append("")
                        new_lines.append(next_line)
                        i += 1
                        break
                    # Stop at end of file
                    if i == len(lines) - 1:
                        in_sources_section = False
                        i += 1
                        break
                    i += 1
                continue
            
            # Regular line - add it if we're not in sources section
            if not in_sources_section:
                new_lines.append(line)
            
            i += 1
        
        # If section wasn't found, append it at the end
        if not section_found:
            # Ensure we end with a newline
            if new_lines and new_lines[-1].strip():
                new_lines.append("")
            new_lines.append("[tool.uv.sources]")
            template_lines = template_content.strip().split("\n")
            for template_line in template_lines:
                template_stripped = template_line.strip()
                # Skip if it's the section header
                if template_stripped == "[tool.uv.sources]":
                    continue
                new_lines.append(template_line)
        
        # Write updated content
        updated_content = "\n".join(new_lines)
        # Ensure file ends with newline
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

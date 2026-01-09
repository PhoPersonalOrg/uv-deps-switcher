"""Configuration file parsing for repo groups."""

import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib


def find_config_file(start_path: Path) -> Optional[Path]:
    """Find .uv-deps-switcher.toml or uv-deps-switcher.toml in current directory or parents."""
    current = start_path.resolve()
    
    # Check current directory and parents up to root
    while current != current.parent:
        for name in [".uv-deps-switcher.toml", "uv-deps-switcher.toml"]:
            config_path = current / name
            if config_path.exists():
                return config_path
        current = current.parent
    
    # Check home directory
    home_config = Path.home() / ".uv-deps-switcher.toml"
    if home_config.exists():
        return home_config
    
    return None


def load_config(config_path: Optional[Path] = None) -> Dict:
    """Load configuration from file."""
    if config_path is None:
        config_path = find_config_file(Path.cwd())
    
    if config_path is None or not config_path.exists():
        return {}
    
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        return config.get("groups", {})
    except Exception as e:
        print(f"Warning: Could not load config file {config_path}: {e}", file=sys.stderr)
        return {}


def get_group_repos(groups: Dict, group_name: str) -> Optional[List[str]]:
    """Get list of repos for a specific group."""
    if group_name not in groups:
        return None
    
    group_config = groups[group_name]
    if isinstance(group_config, dict) and "repos" in group_config:
        return group_config["repos"]
    elif isinstance(group_config, list):
        return group_config
    
    return None


def list_groups(groups: Dict) -> None:
    """List all available groups."""
    if not groups:
        print("No groups defined in configuration file.")
        print("Create a .uv-deps-switcher.toml file with group definitions.")
        return
    
    print("Available groups:")
    for group_name, group_config in groups.items():
        if isinstance(group_config, dict):
            repos = group_config.get("repos", [])
            description = group_config.get("description", "")
            if description:
                print(f"  {group_name}: {description}")
                print(f"    Repos: {', '.join(repos)}")
            else:
                print(f"  {group_name}: {', '.join(repos)}")
        elif isinstance(group_config, list):
            print(f"  {group_name}: {', '.join(group_config)}")

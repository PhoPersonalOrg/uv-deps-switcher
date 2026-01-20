---
name: Merge UV Sources
overview: Modify the `update_pyproject_sources` function to merge template items with existing `[tool.uv.sources]` entries instead of replacing the entire section, preserving any dependencies not listed in the template.
todos:
  - id: parse-template
    content: Add helper to parse template content with tomllib and extract source keys
    status: completed
  - id: extract-key
    content: Add helper function to extract key name from a TOML source line
    status: completed
  - id: merge-logic
    content: Rewrite update_pyproject_sources to merge template items instead of replacing entire section
    status: completed
    dependencies:
      - parse-template
      - extract-key
---

# Merge Template Items Into [tool.uv.sources] Section

## Current Behavior

The `update_pyproject_sources` function in [`src/uv_deps_switcher/main.py`](src/uv_deps_switcher/main.py) completely replaces the `[tool.uv.sources]` section with the template content. This removes any existing entries not in the template.

## Desired Behavior

Only update/add the specific keys that appear in the template, leaving other existing entries intact.

**Example:**

- Existing section has: `dep-a`, `dep-b`, `dep-c`
- Template contains: `dep-a`, `dep-b`
- Result should have: updated `dep-a`, updated `dep-b`, preserved `dep-c`

## Implementation Approach

Modify [`src/uv_deps_switcher/main.py`](src/uv_deps_switcher/main.py) with a hybrid parsing strategy:

1. **Parse template keys using `tomllib`** - Extract the dictionary of source keys from the template to know which entries to update

2. **Line-by-line merge in existing section** - When processing the `[tool.uv.sources]` section:

- For each existing line, check if its key is in the template
- If yes: replace with the template's version
- If no: keep the original line unchanged
- After processing existing lines, add any template keys that weren't already present

3. **Key extraction helper** - Add a small helper to extract the key name from a TOML line (e.g., `some-dep = {...}` -> `some-dep`)

This preserves formatting for untouched entries while applying template updates cleanly.
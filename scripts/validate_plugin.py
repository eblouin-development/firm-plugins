#!/usr/bin/env python3
"""
Validate the dev-lifecycle plugin before it ships.

Deterministic, no-auth structural checks that mirror what Claude Code rejects on
install — the JSON manifests, and (the one that bit us) the YAML frontmatter of
every SKILL.md. Run locally with `python scripts/validate_plugin.py`; runs in CI
on every push and PR. Exits non-zero on any error.
"""
import json
import os
import sys
import glob

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (pip install pyyaml)")
    sys.exit(2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "dev-lifecycle")
ALLOWED_PLUGIN_FIELDS = {
    "name", "version", "description", "author",
    "homepage", "repository", "license", "keywords",
}

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        err(f"missing file: {os.path.relpath(path, ROOT)}")
    except json.JSONDecodeError as e:
        err(f"invalid JSON in {os.path.relpath(path, ROOT)}: {e}")
    return None


# 1. marketplace.json
mkt = load_json(os.path.join(ROOT, ".claude-plugin", "marketplace.json"))
if isinstance(mkt, dict):
    if not mkt.get("name"):
        err("marketplace.json: missing 'name'")
    if not isinstance(mkt.get("owner"), dict):
        err("marketplace.json: 'owner' must be an object")
    plugins = mkt.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        err("marketplace.json: 'plugins' must be a non-empty array")
    else:
        has_root = bool(mkt.get("metadata", {}).get("pluginRoot"))
        for i, p in enumerate(plugins):
            if not p.get("name"):
                err(f"marketplace.json: plugins[{i}] missing 'name'")
            if not p.get("source") and not has_root:
                err(f"marketplace.json: plugins[{i}] missing 'source' "
                    "(and no metadata.pluginRoot set)")

# 2. plugin.json
pj = load_json(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"))
if isinstance(pj, dict):
    for req in ("name", "version", "description"):
        if not pj.get(req):
            err(f"plugin.json: missing required field '{req}'")
    extra = set(pj) - ALLOWED_PLUGIN_FIELDS
    if extra:
        err(f"plugin.json: unsupported field(s) {sorted(extra)} "
            f"(allowed: {sorted(ALLOWED_PLUGIN_FIELDS)})")
    author = pj.get("author")
    if author is not None and not (isinstance(author, dict) and author.get("name")):
        err("plugin.json: 'author' must be an object with a 'name'")

# 3. every SKILL.md frontmatter must be valid YAML with name + description
skills = sorted(glob.glob(os.path.join(PLUGIN, "skills", "*", "SKILL.md")))
if not skills:
    err("no skills found under plugins/dev-lifecycle/skills/")
for path in skills:
    rel = os.path.relpath(path, ROOT)
    skill_dir = os.path.basename(os.path.dirname(path))
    text = open(path).read()
    if not text.startswith("---"):
        err(f"{rel}: missing YAML frontmatter")
        continue
    parts = text.split("---", 2)
    if len(parts) < 3:
        err(f"{rel}: malformed frontmatter (no closing '---')")
        continue
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        err(f"{rel}: invalid YAML frontmatter -> {e}")
        continue
    if not isinstance(data, dict):
        err(f"{rel}: frontmatter is not a mapping")
        continue
    name = data.get("name")
    if not name:
        err(f"{rel}: frontmatter missing 'name'")
    elif name != skill_dir:
        err(f"{rel}: name '{name}' does not match directory '{skill_dir}'")
    if not data.get("description"):
        err(f"{rel}: frontmatter missing 'description'")

# 4. (warning) references should carry a metadata header for the freshness audit
for path in glob.glob(os.path.join(PLUGIN, "references", "**", "*.md"), recursive=True):
    if os.path.basename(path).startswith("_"):
        continue
    head = open(path).read(1000)
    if "last-verified:" not in head:
        warn(f"{os.path.relpath(path, ROOT)}: no 'last-verified' metadata header")

# 4a. (warning) same freshness/header check for real template blocks, once they
#     exist. `_`-prefixed files are schema exemplars (e.g. _TEMPLATE-README.md)
#     and are skipped, matching the references check above. `docs/fragment.md`
#     files are also skipped: the canonical fragment format is machine-consumed
#     (single `<!-- fragment: ... -->` header line, no metadata slot — see
#     references/authoring/documentation-standard.md); freshness for a block or
#     component is carried by its README, which does carry `last-verified`.
#     The glob is empty-dir safe.
for path in glob.glob(os.path.join(PLUGIN, "templates", "**", "*.md"), recursive=True):
    if os.path.basename(path).startswith("_"):
        continue
    if path.endswith(os.path.join("docs", "fragment.md")):
        continue
    head = open(path).read(1000)
    if "last-verified:" not in head:
        warn(f"{os.path.relpath(path, ROOT)}: no 'last-verified' metadata header")

# 5. no hardcoded personal handle in SHARED skill/workflow text. This repo's
#    own CLAUDE.md and .github/pull_request_template.md are allowed to keep a
#    literal `cc @<handle>` convention (it's genuinely this repo's owner and
#    the README documents the substitution on rename); everything that ships
#    to — or is read by — every other repo must not hardcode one owner.
PERSONAL_HANDLE = "eblouin876"
HANDLE_EXEMPT = {
    os.path.join(ROOT, "CLAUDE.md"),
    os.path.join(ROOT, ".github", "pull_request_template.md"),
}
HANDLE_SCAN_GLOBS = [
    os.path.join(PLUGIN, "skills", "**", "*.md"),
    os.path.join(PLUGIN, "assets", "**", "*"),
    os.path.join(ROOT, ".github", "workflows", "*.yml"),
    os.path.join(ROOT, ".github", "workflows", "*.yaml"),
]
for pattern in HANDLE_SCAN_GLOBS:
    for path in glob.glob(pattern, recursive=True):
        if not os.path.isfile(path) or path in HANDLE_EXEMPT:
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        if "@" + PERSONAL_HANDLE in text:
            err(f"{os.path.relpath(path, ROOT)}: hardcodes the personal handle "
                f"'@{PERSONAL_HANDLE}' — shared skill/workflow text must use the "
                "'<owner>' placeholder (or, in a workflow that can, derive it "
                "with '${{ github.repository_owner }}') instead of a literal "
                "personal handle")

# report
for w in warnings:
    print(f"::warning:: {w}" if os.getenv("GITHUB_ACTIONS") else f"WARN  {w}")
if errors:
    print()
    for e in errors:
        print(f"::error:: {e}" if os.getenv("GITHUB_ACTIONS") else f"ERROR {e}")
    print(f"\nValidation FAILED: {len(errors)} error(s), {len(warnings)} warning(s).")
    sys.exit(1)

print(f"Validation passed: {len(skills)} skills, {len(warnings)} warning(s).")

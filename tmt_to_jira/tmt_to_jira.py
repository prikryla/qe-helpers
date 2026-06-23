#!/usr/bin/env python3
"""Export tmt/fmf test metadata to CSV for Jira Cloud Test Case import."""

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

# Directories to skip (tmt plans, not test cases)
SKIP_DIRS = {"Plans", "plans"}


def get_repo_info(root):
    """Detect git remote URL and return (base_url, url_path) for GitHub/GitLab."""
    try:
        url = subprocess.check_output(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, None

    if url.startswith("git@github.com:"):
        slug = url.removeprefix("git@github.com:").removesuffix(".git")
        return f"https://github.com/{slug}", "blob"
    if "gitlab" in url:
        slug = url.split(":", 1)[1].removesuffix(".git") if ":" in url else url
        return f"https://{url.split('@')[1].split(':')[0]}/{slug}" if "@" in url else slug, "-/blob"

    return None, None


def load_fmf(path):
    """Load and parse a single .fmf YAML file."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def collect_tests(root, repo_url, url_path, branch, team=""):
    """Walk all .fmf files in a repo and collect test case data."""
    root = Path(root)

    # Read component name from the root main.fmf
    root_data = {}
    root_main = root / "main.fmf"
    if root_main.exists():
        root_data = load_fmf(root_main)

    component = root_data.get("component", [])
    if isinstance(component, list) and component:
        component = component[0]
    elif isinstance(component, str):
        pass
    else:
        component = root.name

    tests = []

    for fmf_file in sorted(root.rglob("*.fmf")):
        # Skip root-level main.fmf and .fmf/ metadata directory
        if fmf_file.parent == root:
            continue
        if ".fmf" in fmf_file.parts:
            continue

        rel_path = fmf_file.relative_to(root)
        if rel_path.parts[0] in SKIP_DIRS:
            continue

        # Variant .fmf files inherit metadata from their parent main.fmf
        parent_data = {}
        if fmf_file.name != "main.fmf":
            parent_main = fmf_file.parent / "main.fmf"
            if parent_main.exists():
                parent_data = load_fmf(parent_main)

        file_data = load_fmf(fmf_file)
        data = {**parent_data, **file_data}

        # Build test path: /Category/test-name or /Category/test-name/variant
        if fmf_file.name == "main.fmf":
            test_path = f"/{rel_path.parent}"
        else:
            test_path = f"/{rel_path.parent}/{fmf_file.stem}"

        # Summary format: [component] /path/to/test
        summary = f"[{component}] {test_path}"

        description = " ".join(data.get("description", "").split()) or "No description"

        # Sanitize commas to avoid breaking CSV columns
        summary = summary.replace(",", ";")
        description = description.replace(",", ";")

        # Extract assignee email from 'contact' field (format: "Name <email>")
        assignee = ""
        contact = data.get("contact")
        if contact:
            if isinstance(contact, list):
                contact = contact[0]
            email_match = re.search(r"<([^>]+)>", str(contact))
            assignee = email_match.group(1) if email_match else str(contact)

        # Extract tier: first from 'tier' attribute, then from tags (CI-Tier-1, Tier1, etc.)
        tier = ""
        tier_attr = data.get("tier")
        if tier_attr is not None:
            tier = str(tier_attr)
        else:
            for tag in data.get("tag", []):
                m = re.match(r"(?:CI-)?[Tt]ier-?(\d+)", str(tag))
                if m:
                    tier = m.group(1)
                    break

        automation_url = f"{repo_url}/{url_path}/{branch}/{rel_path}"

        tests.append({
            "Issue Type": "Test Case",
            "Summary": summary,
            "Description": description,
            "Components": component,
            "Tier": tier,
            "Assignee": assignee,
            "AssignedTeam": team,
            "Automation URL": automation_url,
        })

    return tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-r", "--root", dest="roots", action="append", required=True,
                        help="Root directory of an fmf tree (can be repeated)")
    parser.add_argument("-b", "--branch", default="master",
                        help="Git branch for Automation URLs (default: master)")
    parser.add_argument("-t", "--team", default="",
                        help="AssignedTeam value (default: empty)")
    parser.add_argument("-o", "--output", default="test_cases.csv",
                        help="Output CSV path (default: test_cases.csv)")
    args = parser.parse_args()

    # Process each repo and merge all tests into one list
    all_tests = []
    for root_arg in args.roots:
        root = Path(root_arg).resolve()
        repo_url, url_path = get_repo_info(root)
        if not repo_url:
            sys.exit(f"Could not determine git remote URL for {root}")
        all_tests.extend(collect_tests(root, repo_url, url_path, args.branch, args.team))

    if not all_tests:
        sys.exit("No fmf test definitions found.")

    # Write CSV output
    fieldnames = ["Issue Type", "Summary", "Description", "Components", "Tier", "Assignee", "AssignedTeam", "Automation URL"]
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_tests)

    print(f"Exported {len(all_tests)} test cases to {args.output}")


if __name__ == "__main__":
    main()

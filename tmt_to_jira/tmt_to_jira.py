#!/usr/bin/env python3
"""Export tmt/fmf test metadata to CSV for Jira Cloud Test Case import."""

import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

SKIP_DIRS = {"Plans", "plans"}


def parse_repo_url(url):
    """Parse a git repo HTTPS URL and return (base_url, url_path) for GitHub/GitLab."""
    stripped = url.removeprefix("https://").removesuffix(".git").rstrip("/")
    base = f"https://{stripped}"
    if "github.com" in url:
        return base, "blob"
    if "gitlab" in url:
        return base, "-/blob"
    return base, "blob"


def clone_repo(url):
    """Shallow-clone a repo into a temp directory, return (path, branch)."""
    tmpdir = tempfile.mkdtemp(prefix="tmt_to_jira_")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", url, tmpdir],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(f"Failed to clone {url}: {e.stderr.strip()}")

    branch = subprocess.check_output(
        ["git", "-C", tmpdir, "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
    ).strip()

    return tmpdir, branch


def load_fmf(path):
    """Load and parse a single .fmf YAML file."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def collect_tests(root, repo_url, url_path, branch, team=""):
    """Walk all .fmf files in a repo and collect test case data."""
    root = Path(root)

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
        if fmf_file.parent == root:
            continue
        if ".fmf" in fmf_file.parts:
            continue

        rel_path = fmf_file.relative_to(root)
        if rel_path.parts[0] in SKIP_DIRS:
            continue

        parent_data = {}
        if fmf_file.name != "main.fmf":
            parent_main = fmf_file.parent / "main.fmf"
            if parent_main.exists():
                parent_data = load_fmf(parent_main)

        file_data = load_fmf(fmf_file)
        data = {**parent_data, **file_data}

        if fmf_file.name == "main.fmf":
            test_path = f"/{rel_path.parent}"
        else:
            test_path = f"/{rel_path.parent}/{fmf_file.stem}"

        summary = f"[{component}] {test_path}"

        description = " ".join(data.get("description", "").split()) or "No description"

        summary = summary.replace(",", ";")
        description = description.replace(",", ";")

        assignee = ""
        contact = data.get("contact")
        if contact:
            if isinstance(contact, list):
                contact = contact[0]
            email_match = re.search(r"<([^>]+)>", str(contact))
            assignee = email_match.group(1) if email_match else str(contact)

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
    parser.add_argument("-r", "--repo", dest="repos", action="append", required=True,
                        help="HTTPS repo URL to clone and scan (can be repeated)")
    parser.add_argument("-t", "--team", default="",
                        help="AssignedTeam value (default: empty)")
    parser.add_argument("-o", "--output", default="test_cases.csv",
                        help="Output CSV path (default: test_cases.csv)")
    args = parser.parse_args()

    all_tests = []
    for repo_url in args.repos:
        print(f"Cloning {repo_url} ...")
        tmpdir, branch = clone_repo(repo_url)
        try:
            base_url, url_path = parse_repo_url(repo_url)
            all_tests.extend(collect_tests(tmpdir, base_url, url_path, branch, args.team))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    if not all_tests:
        sys.exit("No fmf test definitions found.")

    fieldnames = ["Issue Type", "Summary", "Description", "Components", "Tier", "Assignee", "AssignedTeam", "Automation URL"]
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_tests)

    print(f"Exported {len(all_tests)} test cases to {args.output}")


if __name__ == "__main__":
    main()

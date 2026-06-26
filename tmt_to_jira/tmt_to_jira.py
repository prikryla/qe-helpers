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
    sys.exit("ERROR: PyYAML is required: pip install pyyaml")

SKIP_DIRS = {"Plans", "plans"}

# Maps a substring found in the URL to the path segment used for file browsing.
# GitHub uses /blob/, GitLab uses /-/blob/.
# Add new platforms here as needed (e.g. "pkgs.devel.redhat.com": "cgit/...").
URL_PATH_RULES = {
    "github.com": "blob",
    "gitlab": "-/blob",
}


def parse_repo_url(url):
    """Parse a git repo HTTPS URL and return (base_url, url_path)."""
    stripped = url.removeprefix("https://").removesuffix(".git").rstrip("/")
    base = f"https://{stripped}"
    for pattern, path in URL_PATH_RULES.items():
        if pattern in url:
            return base, path
    print(f"WARNING: Unknown git platform for {url}, Automation URLs may be incorrect")
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
        sys.exit(f"ERROR: Failed to clone {url}\n{e.stderr.strip()}")
    except FileNotFoundError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit("ERROR: git is not installed or not found in PATH")

    try:
        branch = subprocess.check_output(
            ["git", "-C", tmpdir, "rev-parse", "--abbrev-ref", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(f"ERROR: Could not detect default branch for {url}")

    return tmpdir, branch


def load_fmf(path):
    """Load and parse a single .fmf YAML file."""
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"WARNING: Failed to parse {path}: {e}")
        return {}
    except OSError as e:
        print(f"WARNING: Could not read {path}: {e}")
        return {}


def collect_tests(root, repo_url, url_path, branch, team=""):
    """Walk all .fmf files in a repo and collect test case data."""
    root = Path(root)

    fmf_dir = root / ".fmf"
    if not fmf_dir.exists():
        print(f"WARNING: No .fmf/ directory in {repo_url}, skipping")
        return []

    root_data = {}
    root_main = root / "main.fmf"
    if root_main.exists():
        root_data = load_fmf(root_main)
    else:
        print(f"WARNING: No root main.fmf in {repo_url}, component will default to repo name")

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
        if not file_data and not parent_data:
            continue
        data = {**parent_data, **file_data}

        if fmf_file.name == "main.fmf":
            test_path = f"/{rel_path.parent}"
        else:
            test_path = f"/{rel_path.parent}/{fmf_file.stem}"

        summary = f"[{component}] {test_path}"

        description = data.get("description", "")
        if isinstance(description, str):
            description = " ".join(description.split()) or "No description"
        else:
            description = "No description"

        summary = summary.replace(",", ";")
        description = description.replace(",", ";")

        assignee = ""
        contact = data.get("contact")
        if contact:
            if isinstance(contact, list):
                contact = contact[0] if contact else ""
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

    if not tests:
        print(f"WARNING: No test definitions found in {repo_url}")

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

    for url in args.repos:
        if not url.startswith("https://"):
            sys.exit(f"ERROR: Only HTTPS URLs are supported: {url}")

    all_tests = []
    errors = []
    for repo_url in args.repos:
        print(f"Cloning {repo_url} ...")
        tmpdir, branch = clone_repo(repo_url)
        try:
            base_url, url_path = parse_repo_url(repo_url)
            tests = collect_tests(tmpdir, base_url, url_path, branch, args.team)
            print(f"  Found {len(tests)} test(s) on branch '{branch}'")
            all_tests.extend(tests)
        except Exception as e:
            errors.append(f"{repo_url}: {e}")
            print(f"ERROR: Failed to process {repo_url}: {e}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    if errors:
        print(f"\n{len(errors)} repo(s) had errors:")
        for err in errors:
            print(f"  - {err}")

    if not all_tests:
        sys.exit("ERROR: No fmf test definitions found in any repository.")

    try:
        fieldnames = ["Issue Type", "Summary", "Description", "Components", "Tier", "Assignee", "AssignedTeam", "Automation URL"]
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_tests)
    except OSError as e:
        sys.exit(f"ERROR: Could not write output file {args.output}: {e}")

    print(f"\nExported {len(all_tests)} test cases to {args.output}")


if __name__ == "__main__":
    main()

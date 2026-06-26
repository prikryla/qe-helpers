# tmt_to_jira

Export tmt/fmf test metadata into a CSV file ready for Jira Cloud Test Case import.

## Requirements

- Python 3.9+
- [PyYAML](https://pypi.org/project/PyYAML/)
- Git

```bash
pip install pyyaml
```

Each target repository must contain:
- A `.fmf/` directory (FMF version file)
- A root `main.fmf` with a `component` field
- Test definitions as `*.fmf` files under subdirectories

## Usage

```bash
python3 tmt_to_jira.py -r <repo-url> -o test_cases.csv
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-r`, `--repo` | Git repo URL to clone and scan (can be repeated) | *required* |
| `-o`, `--output` | Output CSV file path | `test_cases.csv` |
| `-t`, `--team` | AssignedTeam value for all exported tests | *empty* |

### Examples

Single repository:

```bash
python3 tmt_to_jira.py -r https://github.com/RedHat-SP-Security/aide-tests -o test_cases.csv
```

Multiple repositories with a team:

```bash
python3 tmt_to_jira.py \
  -r https://github.com/RedHat-SP-Security/aide-tests \
  -r git@gitlab.cee.redhat.com:special-projects/tests/aide.git \
  -t "rhel-security-special-projects" \
  -o test_cases.csv
```

SSH URLs work too:

```bash
python3 tmt_to_jira.py -r git@github.com:RedHat-SP-Security/aide-tests.git
```

## CSV Output

The generated CSV contains the following columns:

| Column | Description |
|--------|-------------|
| Issue Type | Always `Test Case` |
| Summary | `[component] /path/to/test` |
| Description | Test description from fmf metadata, or `No description` |
| Components | Component name from the root `main.fmf` |
| Tier | Test tier (1, 2, or 3) extracted from fmf metadata, or empty |
| Assignee | Email extracted from the `contact` field in fmf metadata, or empty |
| AssignedTeam | Value from `--team`, or empty |
| Automation URL | Link to the `.fmf` file in the git repository |

### How it works

- Clones each repository into a temporary directory (shallow clone for speed)
- Auto-detects the default branch (main or master) for Automation URLs
- Reads the `component` field from the root `main.fmf` of each repository
- Walks all `*.fmf` files, skipping the `Plans/` directory
- Variant `.fmf` files (non-`main.fmf`) inherit metadata from their parent `main.fmf`
- Extracts the test tier from multiple sources (in priority order):
  1. `tier` attribute (e.g., `tier: '1'`)
  2. Tags: `CI-Tier-1`, `CI-Tier-2`, `CI-Tier-3`
  3. Tags: `Tier1`, `Tier2`, `Tier3` (including variants like `Tier1security`)
- Commas in Summary and Description fields are replaced with semicolons
- Newlines in descriptions are collapsed to single-line text
- Temporary clones are cleaned up automatically after scanning

## Supported repositories

The script auto-detects the git hosting platform from the URL:

- **GitHub** (`github.com`) — Automation URLs use `/blob/`
- **GitLab** (`gitlab.*`) — Automation URLs use `/-/blob/`

# tmt_to_jira

Export tmt/fmf test metadata into a CSV file ready for Jira Cloud Test Case import.

## Requirements

- Python 3.9+
- [PyYAML](https://pypi.org/project/PyYAML/)

```bash
pip install pyyaml
```

Each target directory must be a git repository with:
- A `.fmf/` directory (FMF version file)
- A root `main.fmf` with a `component` field
- Test definitions as `*.fmf` files under subdirectories

## Usage

```bash
python3 tmt_to_jira.py -r /path/to/repo -o test_cases.csv
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-r`, `--root` | Root directory of an fmf tree (can be repeated) | *required* |
| `-o`, `--output` | Output CSV file path | *required* |
| `-b`, `--branch` | Git branch used in Automation URLs | `master` |
| `-t`, `--team` | AssignedTeam value for all exported tests | *empty* |

### Examples

Single repository:

```bash
python3 tmt_to_jira.py -r /path/to/aide-tests -o test_cases.csv
```

Multiple repositories with a team:

```bash
python3 tmt_to_jira.py \
  -r /path/to/aide-tests \
  -r /path/to/another-component-tests \
  -t "rhel-security-special-projects" \
  -o test_cases.csv
```

Custom branch:

```bash
python3 tmt_to_jira.py -r /path/to/repo -b main -o test_cases.csv
```

## CSV Output

The generated CSV contains the following columns:

| Column | Description |
|--------|-------------|
| Issue Type | Always `Test` |
| Summary | `[component] /path/to/test` |
| Description | Test description from fmf metadata, or `No description` |
| Components | Component name from the root `main.fmf` |
| AssignedTeam | Value from `--team`, or empty |
| Automation URL | Link to the `.fmf` file in the git repository |

### How it works

- Reads the `component` field from the root `main.fmf` of each repository
- Walks all `*.fmf` files, skipping the `Plans/` directory
- Variant `.fmf` files (non-`main.fmf`) inherit metadata from their parent `main.fmf`
- Auto-detects GitHub and GitLab remotes to build Automation URLs
- Commas in Summary and Description fields are replaced with semicolons
- Newlines in descriptions are collapsed to single-line text

## Supported repositories

The script auto-detects the git remote type:

- **GitHub** (`git@github.com:...`) — URLs use `/blob/`
- **GitLab** (`git@gitlab...:...`) — URLs use `/-/blob/`

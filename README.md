# Stoneshard Toolsv2

Standalone repository for the current `toolsv2` solver, layout, and base-render stack.

This repo intentionally includes only:
- the current `toolsv2` source modules
- the current `toolsv2/tests` suite
- the current contract/design docs inside `toolsv2`
- the current source art primitives, examples, and extractor inputs/reports used by the maintained toolsv2 flow

This repo intentionally excludes:
- legacy prototype code
- logs, caches, generated renders, and extractor build byproducts
- anything outside the current `toolsv2` project boundary

## Setup

### PowerShell

```powershell
.\scripts\setup.ps1
```

### Bash

```bash
./scripts/setup.sh
```

### Manual

```bash
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

On Unix-like systems, use `.venv/bin/python` instead.

## Run Tests

```bash
python -m unittest discover -s toolsv2/tests -v
```

## Run Example

```bash
python -m toolsv2.run_branch toolsv2/examples/test_branch.json
```

By default this writes the base render to `toolsv2/output/<tree_id>.png`.

## CI

GitHub Actions runs the same unittest suite on every push and pull request.

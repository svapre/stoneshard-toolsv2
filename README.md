# Stoneshard Toolsv2

Standalone repository for the current locked `toolsv2` solver/runtime stack.

This repo intentionally includes only:
- the current `toolsv2` source modules
- the current `toolsv2/tests` suite
- the current contract/design docs inside `toolsv2`

This repo intentionally excludes:
- legacy prototype code
- sprites, art assets, logs, examples, and local extraction tools
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

## CI

GitHub Actions runs the same unittest suite on every push and pull request.

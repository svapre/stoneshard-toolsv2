$ErrorActionPreference = "Stop"

$venvPath = ".venv"

python -m venv $venvPath
& (Join-Path $venvPath "Scripts\\python.exe") -m pip install --upgrade pip
& (Join-Path $venvPath "Scripts\\python.exe") -m pip install -r requirements-dev.txt

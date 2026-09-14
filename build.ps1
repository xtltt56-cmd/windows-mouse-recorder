$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonCommand = "python"
$pythonArguments = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 --version *> $null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = "py"
        $pythonArguments = @("-3.12")
    }
}

$buildEnvironment = Join-Path $projectRoot ".venv-build"
$buildPython = Join-Path $buildEnvironment "Scripts\python.exe"

Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $buildPython)) {
        & $pythonCommand @pythonArguments -m venv $buildEnvironment
        if ($LASTEXITCODE -ne 0) {
            throw "Build environment creation failed with exit code $LASTEXITCODE"
        }
    }

    & $buildPython -m pip install --disable-pip-version-check -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed with exit code $LASTEXITCODE"
    }

    & $buildPython -m PyInstaller --noconfirm --clean --onefile --windowed --name MouseClicker main.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    Write-Host "Built dist\MouseClicker.exe"
} finally {
    Pop-Location
}

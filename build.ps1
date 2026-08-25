$ErrorActionPreference = "Stop"
$pythonCommand = "python"
$pythonArguments = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 --version *> $null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = "py"
        $pythonArguments = @("-3.12")
    }
}
& $pythonCommand @pythonArguments -m pip install -r requirements.txt
& $pythonCommand @pythonArguments -m pip install pyinstaller
& $pythonCommand @pythonArguments -m PyInstaller --noconfirm --clean --onefile --windowed --name MouseClicker main.py
Write-Host "Built dist\MouseClicker.exe"

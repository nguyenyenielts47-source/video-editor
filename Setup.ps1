$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path '.tools\python\python.exe') {
    $pythonExe = Join-Path $PSScriptRoot '.tools\python\python.exe'
} elseif (Test-Path '.venv\Scripts\python.exe') {
    $pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
} else {
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install 64-bit Python 3.12 with pip and Tcl/Tk, then retry.' }
    $pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
}
& $pythonExe -m pip install --upgrade -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $pythonExe -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
& $pythonExe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed. See the messages above.' }
Write-Host 'Update complete. Double-click Launch.bat.'

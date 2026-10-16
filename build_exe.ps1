# Builds StatisticBuddy.exe and a zip for the GitHub Releases page.
#
# Usage (from the project folder, in PowerShell):
#   .\build_exe.ps1                     # uses the Python environment from run.bat
#   .\build_exe.ps1 -Python C:\path\to\python.exe
#
# Output: dist\StatisticBuddy\StatisticBuddy.exe  and  dist\StatisticBuddy-<version>-windows.zip
param(
    [string]$Python = "$env:LOCALAPPDATA\StatisticBuddy\venv\Scripts\python.exe"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path $Python)) { throw "Python not found at $Python. Run run.bat once first, or pass -Python." }

& $Python -m pip install --quiet -r requirements.txt pyinstaller==6.11.1
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$version = & $Python -c "import statisticbuddy; print(statisticbuddy.__version__)"

& $Python -m PyInstaller --noconfirm --clean --windowed `
    --name StatisticBuddy `
    --distpath dist --workpath build\work --specpath build `
    --paths . `
    --collect-submodules numpy `
    --collect-data rapidocr_onnxruntime `
    --collect-binaries onnxruntime `
    --exclude-module tkinter --exclude-module matplotlib `
    packaging\launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Not used by the app (~50 MB): OpenCV's video codec library and Qt's software OpenGL fallback.
Get-ChildItem dist\StatisticBuddy\_internal -Recurse -Include "opencv_videoio_ffmpeg*.dll", "opengl32sw.dll" |
    Remove-Item -Force

Copy-Item README.md, LICENSE dist\StatisticBuddy\
$zip = "dist\StatisticBuddy-$version-windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\StatisticBuddy -DestinationPath $zip
Write-Host "Built $zip"

# Check the packaged OCR and digit reader actually work (uses a throwaway data folder).
$env:STATISTICBUDDY_DATA_DIR = Join-Path $env:TEMP "statisticbuddy-selftest"
$p = Start-Process -FilePath dist\StatisticBuddy\StatisticBuddy.exe -ArgumentList "--selftest" -PassThru -Wait
Get-Content "$env:STATISTICBUDDY_DATA_DIR\app.log" -Tail 1
if ($p.ExitCode -ne 0) { throw "Self-test of the packaged app failed" }
Write-Host "Self-test passed"

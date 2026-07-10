# build.ps1 - produce a single portable Folder2PDF.exe
# Run once on a build machine that has Python 3.9+.
# Output: .\dist\Folder2PDF.exe  (no Python needed on target machines)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install img2pdf pillow pyinstaller tkinterdnd2

# --noconsole: no console window flashes on right-click
# --onefile:   single distributable exe
# --exclude-module: drop heavyweight libs img2pdf/PIL never use. numpy is the big
#   one — in Anaconda it drags in ~200MB of MKL DLLs. pikepdf/lxml stay (required).
pyinstaller --onefile --noconsole --name Folder2PDF --clean `
    --collect-submodules img2pdf `
    --collect-submodules PIL `
    --collect-all tkinterdnd2 `
    --exclude-module numpy `
    --exclude-module scipy `
    --exclude-module pandas `
    --exclude-module matplotlib `
    --exclude-module PIL.ImageTk `
    --exclude-module IPython `
    --exclude-module notebook `
    folder2pdf.py

Write-Host ""
Write-Host "Built: $PSScriptRoot\dist\Folder2PDF.exe"
Write-Host "Next: copy it to a permanent location, then run it."

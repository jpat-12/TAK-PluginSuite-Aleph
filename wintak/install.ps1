<#
  install.ps1 — build (optional) and install the Aleph WinTAK plugin.

  WinTAK loads plugins as single DLLs from <WinTAK>\Plugins, which lives under Program Files,
  so this needs an elevated PowerShell. Close WinTAK first (it locks loaded plugin DLLs); the
  plugin appears as Home → Tools → "Aleph Capture" on the next start.

    .\wintak\install.ps1                 # build Release against the installed WinTAK, then install
    .\wintak\install.ps1 -NoBuild        # install an already-built (or downloaded) AlephWinTak.dll
    .\wintak\install.ps1 -Remove         # uninstall (your settings in %LOCALAPPDATA%\AlephWinTak stay)
    .\wintak\install.ps1 -WinTakDir "D:\WinTAK"
#>
param(
    [string]$WinTakDir = "C:\Program Files\WinTAK",
    [switch]$NoBuild,
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $WinTakDir "Plugins\AlephWinTak.dll"

if (-not (Test-Path (Join-Path $WinTakDir "WinTAK.exe"))) { throw "WinTAK not found at $WinTakDir (use -WinTakDir)." }
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Run this from an elevated PowerShell (Run as administrator) — it writes to $WinTakDir\Plugins." }
if (Get-Process WinTAK -ErrorAction SilentlyContinue) { throw "Close WinTAK first; it locks plugin DLLs while running." }

if ($Remove) {
    Remove-Item $target -ErrorAction SilentlyContinue
    Write-Host "Removed $target"
    return
}

$dll = Join-Path $here "AlephWinTak\bin\Release\AlephWinTak.dll"
if (-not $NoBuild) {
    dotnet build (Join-Path $here "AlephWinTak") -c Release -nologo -p:WinTakDir="$WinTakDir"
    if ($LASTEXITCODE -ne 0) { throw "Build failed." }
}
if (-not (Test-Path $dll)) { throw "No $dll — build first or drop the DLL there." }
Copy-Item $dll $target -Force
Write-Host "Installed $(([Reflection.AssemblyName]::GetAssemblyName($target)).Version) → $target"
Write-Host "Start WinTAK → Home → Tools → Aleph Capture."

# install.ps1 — Install the Stock Assets plugin for pi (PowerShell)
# Idempotent: safe to run multiple times.
#
# Installs:
#   1. pi extension  → ~/.pi/agent/extensions/pixabay/     (MCP server + /pixabay command)
#   2. skill         → ~/.agents/skills/stock-assets/      (shared by ALL agent harnesses)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$UserProfile = [Environment]::GetFolderPath("UserProfile")

function Install-JunctionOrCopy {
    param([string]$Src, [string]$Dest, [string]$Name)
    $destParent = Split-Path -Parent $Dest
    if (-not (Test-Path $destParent)) {
        New-Item -ItemType Directory -Path $destParent -Force | Out-Null
    }

    if (Test-Path $Dest) {
        $item = Get-Item $Dest -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            Write-Host "Removing existing junction/symlink: $Dest"
            Remove-Item $Dest -Force
        } else {
            Write-Host "ERROR: $Dest exists as a real directory."
            Write-Host "Remove it manually: Remove-Item -Recurse -Force '$Dest'"
            exit 1
        }
    }

    try {
        New-Item -ItemType Junction -Path $Dest -Target $Src | Out-Null
        Write-Host "Created junction: $Dest -> $Src"
    } catch {
        Write-Host "Junction failed, falling back to copy"
        Copy-Item -Recurse $Src $Dest
        Write-Host "Copied: $Dest"
    }
}

# 1. pi extension
Install-JunctionOrCopy `
    -Src (Join-Path $ScriptDir "extension") `
    -Dest (Join-Path $UserProfile ".pi\agent\extensions\pixabay") `
    -Name "extension"

# 2. skill (shared .agents location)
Install-JunctionOrCopy `
    -Src (Join-Path $ScriptDir "skills\stock-assets") `
    -Dest (Join-Path $UserProfile ".agents\skills\stock-assets") `
    -Name "skill"

Write-Host ""
Write-Host "Stock Assets plugin installed:"
Write-Host "  extension: $UserProfile\.pi\agent\extensions\pixabay"
Write-Host "  skill:     $UserProfile\.agents\skills\stock-assets"
Write-Host ""
Write-Host "Restart pi or run /reload to activate."

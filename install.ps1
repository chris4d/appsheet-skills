param(
    [string]$Source = "C:\dev\appsheet-skills\skills",
    [string]$Destination = "$env:USERPROFILE\.config\opencode\skills",
    [switch]$ProjectLocal
)

$ErrorActionPreference = "Stop"

if ($ProjectLocal) {
    $Destination = Join-Path (Get-Location) ".opencode\skills"
}

$skills = @(
    "appsheet-appdef",
    "appsheet-editor",
    "appsheet-build",
    "appsheet-patterns"
)

if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
}

foreach ($name in $skills) {
    $src = Join-Path $Source $name
    if (-not (Test-Path $src)) {
        throw "Skill source not found: $src"
    }
    $dst = Join-Path $Destination $name
    if (Test-Path $dst) {
        Remove-Item -Recurse -Force $dst
    }
    Copy-Item -Path $src -Destination $dst -Recurse -Force
    Get-ChildItem -Recurse -Directory $dst -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Write-Host "installed $name -> $dst"
}

Write-Host ""
Write-Host "Installed $($skills.Count) AppSheet skills into $Destination"

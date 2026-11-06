param(
    [Parameter(Mandatory = $true)]
    [string]$Appdef,

    [string]$Dir = "appdef",

    [string]$Label = "snapshot",

    [switch]$Compress,

    [int]$Prune = 10,

    [switch]$NoCurrent
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cli = Join-Path $here "appdef.py"

if (-not (Test-Path $Appdef)) {
    throw "Appdef not found: $Appdef"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    $pyExe = $python.Source
    $pyPrefix = @()
} else {
    $pyExe = "py"
    $pyPrefix = @("-3")
}

New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = Join-Path $Dir "$stamp-$Label.json"

# Compact, not pretty-printed: the raw appdef is 1-2 MB pretty, ~1.3 MB compact.
& $pyExe @pyPrefix -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8-sig')); json.dump(d,open(sys.argv[2],'w',encoding='utf-8'),separators=(',',':'),ensure_ascii=False)" $Appdef $dest
if ($LASTEXITCODE -ne 0) {
    throw "Failed to compact appdef"
}

# The rolling baseline is the cheap, always-current copy.
if (-not $NoCurrent) {
    Copy-Item $dest (Join-Path $Dir "current.json") -Force
}

# Sort by the timestamp-prefixed filename, not LastWriteTime: Copy-Item resets it.
$prev = Get-ChildItem $Dir -File |
    Where-Object {
        $_.Name -match '^\d{8}-\d{6}-.*\.json(\.gz)?$' -and
        $_.Name -ne (Split-Path $dest -Leaf)
    } |
    Sort-Object Name -Descending |
    Select-Object -First 1

Write-Host "Snapshot: $dest"
& $pyExe @pyPrefix $cli summary $dest
Write-Host ""

if ($prev) {
    $prevPath = $prev.FullName
    $temp = $null
    if ($prev.Extension -eq ".gz") {
        $temp = [System.IO.Path]::GetTempFileName()
        $in = [System.IO.File]::OpenRead($prevPath)
        $out = [System.IO.File]::Create($temp)
        $gz = New-Object System.IO.Compression.GZipStream($in, [System.IO.Compression.CompressionMode]::Decompress)
        $gz.CopyTo($out)
        $gz.Dispose(); $out.Dispose(); $in.Dispose()
        $prevPath = $temp
    }
    Write-Host "Diff against $($prev.Name):"
    & $pyExe @pyPrefix $cli diff $prevPath $dest
    Write-Host ""
    if ($temp) { Remove-Item $temp -Force }
}

& $pyExe @pyPrefix $cli validate $dest

if ($Compress) {
    $gzPath = "$dest.gz"
    $in = [System.IO.File]::OpenRead($dest)
    $out = [System.IO.File]::Create($gzPath)
    $gz = New-Object System.IO.Compression.GZipStream($out, [System.IO.Compression.CompressionLevel]::Optimal)
    $in.CopyTo($gz)
    $gz.Dispose(); $out.Dispose(); $in.Dispose()
    Remove-Item $dest -Force
    Write-Host "Compressed: $gzPath"
}

if ($Prune -gt 0) {
    $old = Get-ChildItem $Dir -File |
        Where-Object { $_.Name -match '^\d{8}-\d{6}-.*\.json(\.gz)?$' } |
        Sort-Object Name -Descending |
        Select-Object -Skip $Prune
    foreach ($f in $old) {
        Remove-Item $f.FullName -Force
        Write-Host "Pruned: $($f.Name)"
    }
}

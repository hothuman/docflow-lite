param([string]$Destination = (Join-Path (Split-Path $PSScriptRoot -Parent) 'build/python-sdk-3.14.10'))
$ErrorActionPreference = 'Stop'
$version = '3.14.10'
$expected = 'f54ba67c9951c3d773ea47d2bb095150c037c399f0423a968bcda22809241784'
$url = 'https://api.nuget.org/v3-flatcontainer/python/3.14.10/python.3.14.10.nupkg'
$Destination = [System.IO.Path]::GetFullPath($Destination)
$python = Join-Path $Destination 'tools/python.exe'
if (Test-Path -LiteralPath $Destination) {
    if (-not (Test-Path -LiteralPath (Join-Path $Destination 'SDK-INFO.json'))) { throw 'Refusing an unrelated existing SDK directory' }
    $info = Get-Content -LiteralPath (Join-Path $Destination 'SDK-INFO.json') -Raw | ConvertFrom-Json
    if ($info.sha256 -ne $expected) { throw 'Existing SDK provenance differs' }
} else {
    $parent = Split-Path $Destination -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $archive = Join-Path $parent ('python-sdk-' + [guid]::NewGuid().ToString('N') + '.zip')
    Invoke-WebRequest -Uri $url -OutFile $archive
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'Official Python SDK checksum mismatch' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($archive,$Destination)
    @{version=$version;url=$url;sha256=$expected;registry_changes=$false;path_changes=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Destination 'SDK-INFO.json') -Encoding utf8
    Remove-Item -LiteralPath $archive
}
$signature = Get-AuthenticodeSignature -LiteralPath $python
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Python executable signature is not valid PSF' }
& $python -c "import sys; assert sys.version_info[:3] == (3,14,10)"
if ($LASTEXITCODE -ne 0) { throw 'Unexpected build interpreter' }
Write-Output $python

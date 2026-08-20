param(
    [string]$Destination = (Join-Path $PSScriptRoot "..\src\Whispers\tools")
)

$ErrorActionPreference = "Stop"
$url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-08-20-13-45/ffmpeg-n8.1.2-44-g7c533d0f86-win64-lgpl-8.1.zip"
$expectedSha256 = "4fbc721c0168c2c7bc5f665fe4b5bbda2a098e701602cb4237d5390b1c6fb148"
$archive = Join-Path ([IO.Path]::GetTempPath()) "whispers-ffmpeg.zip"
$expanded = Join-Path ([IO.Path]::GetTempPath()) ("whispers-ffmpeg-" + [guid]::NewGuid().ToString("N"))

try {
    Invoke-WebRequest $url -OutFile $archive
    $actualSha256 = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $expectedSha256) {
        throw "FFmpeg SHA-256 inválido: $actualSha256"
    }

    Expand-Archive $archive $expanded
    New-Item -ItemType Directory -Force $Destination | Out-Null
    foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
        $source = Get-ChildItem $expanded -Recurse -File -Filter $name | Select-Object -First 1
        if (-not $source) { throw "$name não encontrado no pacote." }
        Copy-Item $source.FullName (Join-Path $Destination $name) -Force
    }
}
finally {
    Remove-Item $archive -Force -ErrorAction SilentlyContinue
    Remove-Item $expanded -Recurse -Force -ErrorAction SilentlyContinue
}

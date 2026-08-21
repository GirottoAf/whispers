param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,

    [Parameter(Mandatory = $true)]
    [string]$InstallDirectory
)

$ErrorActionPreference = "Stop"
$installerPath = (Resolve-Path $Installer).Path
$InstallDirectory = [IO.Path]::GetFullPath($InstallDirectory)
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if (-not $InstallDirectory.StartsWith($localAppData, [StringComparison]::OrdinalIgnoreCase) -or
    -not (Split-Path $InstallDirectory -Leaf).StartsWith("Whispers-ci-", [StringComparison]::OrdinalIgnoreCase)) {
    throw "O diretório do smoke test deve ser Whispers-ci-* dentro de LocalAppData."
}

$documentsDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
if ([string]::IsNullOrWhiteSpace($documentsDirectory)) {
    throw "O Windows não informou a pasta Documentos do usuário."
}

$outputDirectory = Join-Path $documentsDirectory "Whispers"
$markerPath = Join-Path $outputDirectory "whispers-ci-preserve.txt"
$appProcess = $null
$oldDotnetRoot = $env:DOTNET_ROOT
$oldDotnetRootX64 = $env:DOTNET_ROOT_X64
$oldMultilevelLookup = $env:DOTNET_MULTILEVEL_LOOKUP
$oldPath = $env:PATH

function Invoke-CheckedProcess {
    param([string]$FilePath, [string[]]$ArgumentList)

    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "$FilePath retornou o código $($process.ExitCode)."
    }
}

function Install-Whispers {
    Invoke-CheckedProcess $installerPath @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/DIR=`"$InstallDirectory`""
    )
}

try {
    Remove-Item $InstallDirectory -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $outputDirectory) {
        throw "Pré-condição inválida: Documentos\Whispers já existe no runner limpo."
    }

    Install-Whispers
    python tests/verify_publish_layout.py $InstallDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "A instalação não contém todas as dependências esperadas."
    }
    if (-not (Test-Path $outputDirectory -PathType Container)) {
        throw "O instalador não criou Documentos\Whispers."
    }

    foreach ($tool in @("ffmpeg.exe", "ffprobe.exe")) {
        Invoke-CheckedProcess (Join-Path $InstallDirectory "tools\$tool") @("-version")
    }

    $missingDotnet = Join-Path $InstallDirectory "__dotnet_global_inexistente__"
    $env:DOTNET_ROOT = $missingDotnet
    $env:DOTNET_ROOT_X64 = $missingDotnet
    $env:DOTNET_MULTILEVEL_LOOKUP = "0"
    $env:PATH = (($env:PATH -split ";") | Where-Object { $_ -notmatch "[\\/]dotnet[\\/]?$" }) -join ";"
    $appProcess = Start-Process -FilePath (Join-Path $InstallDirectory "Whispers.exe") -PassThru
    Start-Sleep -Seconds 5
    $appProcess.Refresh()
    if ($appProcess.HasExited) {
        throw "Whispers.exe encerrou durante o smoke test (código $($appProcess.ExitCode))."
    }
    Stop-Process -Id $appProcess.Id -Force
    $appProcess.WaitForExit()
    $appProcess = $null

    Set-Content -Path $markerPath -Value "preservar" -Encoding utf8
    Install-Whispers
    if (-not (Test-Path $markerPath -PathType Leaf)) {
        throw "A atualização removeu o TXT de teste."
    }

    $uninstaller = Join-Path $InstallDirectory "unins000.exe"
    Invoke-CheckedProcess $uninstaller @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
    if (Test-Path (Join-Path $InstallDirectory "Whispers.exe")) {
        throw "A desinstalação não removeu o aplicativo."
    }
    if (-not (Test-Path $markerPath -PathType Leaf)) {
        throw "A desinstalação removeu um TXT do usuário."
    }

    Write-Output "Installer smoke test: OK"
}
finally {
    if ($null -ne $appProcess -and -not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
    }
    $env:DOTNET_ROOT = $oldDotnetRoot
    $env:DOTNET_ROOT_X64 = $oldDotnetRootX64
    $env:DOTNET_MULTILEVEL_LOOKUP = $oldMultilevelLookup
    $env:PATH = $oldPath
    Remove-Item $markerPath -Force -ErrorAction SilentlyContinue
    if (Test-Path (Join-Path $InstallDirectory "unins000.exe")) {
        Start-Process -FilePath (Join-Path $InstallDirectory "unins000.exe") `
            -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait
    }
    Remove-Item $InstallDirectory -Recurse -Force -ErrorAction SilentlyContinue
}

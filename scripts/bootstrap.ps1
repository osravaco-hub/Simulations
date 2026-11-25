<#
.SYNOPSIS
    Prepara (o repara) el entorno de desarrollo de Rig Studio. Idempotente.

.DESCRIPTION
    Crea o reutiliza `.venv`, valida las versiones mínimas (Python 3.11+,
    rustc >= 1.88 con host MSVC, maturin), instala las dependencias y el
    proyecto en modo editable, y compila la extensión nativa SOLO si el
    artefacto instalado es más antiguo que `core_rust/src` (o si no existe).

    No modifica nada fuera del proyecto ni del entorno virtual.

.PARAMETER AllowForwardAbi
    Exporta PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 para esta ejecución. Sirve
    cuando el intérprete es más nuevo que el `abi3` soportado por PyO3.

.PARAMETER SkipRust
    Omite la comprobación de `rustc` (útil si solo se va a trabajar en Python).

.PARAMETER Force
    Recompila la extensión nativa aunque el artefacto esté al día.

.EXAMPLE
    .\scripts\bootstrap.ps1
#>
[CmdletBinding()]
param(
    [switch]$AllowForwardAbi,
    [switch]$SkipRust,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$VenvMaturin = Join-Path $Venv 'Scripts\maturin.exe'

function Write-Step([string]$Mensaje) {
    Write-Host ""
    Write-Host "==> $Mensaje" -ForegroundColor Cyan
}

function Write-Ok([string]$Mensaje) {
    Write-Host "    OK  $Mensaje" -ForegroundColor Green
}

function Write-Info([string]$Mensaje) {
    Write-Host "        $Mensaje" -ForegroundColor DarkGray
}

function Stop-Bootstrap([string]$Mensaje) {
    Write-Host ""
    Write-Host "[ERROR] $Mensaje" -ForegroundColor Red
    exit 1
}

function Invoke-Checked([string]$Exe, [string[]]$ArgumentList, [string]$Que) {
    & $Exe @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        Stop-Bootstrap "$Que (código de salida $LASTEXITCODE)"
    }
}

Write-Host "Rig Studio — bootstrap del entorno de desarrollo" -ForegroundColor White
Write-Info "raíz del proyecto: $Root"

# --------------------------------------------------------------------- Rust
if (-not $SkipRust) {
    Write-Step 'Comprobando el toolchain de Rust'
    $rustc = Get-Command rustc -ErrorAction SilentlyContinue
    if (-not $rustc) {
        Stop-Bootstrap @'
No se encontró 'rustc'. Instálalo con una de estas opciones:

  winget install Rustlang.Rustup
  # o descarga el instalador desde https://rustup.rs

Después:  rustup default stable-msvc
Si no tienes enlazador de C++, instala las Build Tools de Visual Studio:
  winget install Microsoft.VisualStudio.2022.BuildTools
  (carga de trabajo "Desarrollo para el escritorio con C++")

Puedes omitir esta comprobación con -SkipRust.
'@
    }

    $info = & rustc -vV
    if ($LASTEXITCODE -ne 0) { Stop-Bootstrap "'rustc -vV' falló; revisa la instalación de Rust." }
    $release = ($info | Where-Object { $_ -like 'release: *' }) -replace '^release: ', ''
    $hostTriple = ($info | Where-Object { $_ -like 'host: *' }) -replace '^host: ', ''
    if (-not $release -or -not $hostTriple) { Stop-Bootstrap "No se pudo interpretar la salida de 'rustc -vV'." }

    $numeros = $release -replace '[^0-9.].*$', ''
    $actual = [version]$numeros
    if ($actual -lt [version]'1.88') {
        Stop-Bootstrap @"
rustc $release es anterior a la versión mínima 1.88 (RF-03/CA-04).

Actualiza el toolchain:
  rustup update stable
"@
    }
    Write-Ok "rustc $release"

    if ($hostTriple -notmatch 'msvc$') {
        Stop-Bootstrap @"
El host de Rust es '$hostTriple', pero en Windows se necesita uno MSVC.

Instala el toolchain correcto:
  rustup toolchain install stable-x86_64-pc-windows-msvc
  rustup default stable-msvc

Si el enlazador falla, instala las Build Tools de Visual Studio:
  winget install Microsoft.VisualStudio.2022.BuildTools
"@
    }
    Write-Ok "host $hostTriple"
} else {
    Write-Info 'comprobación de Rust omitida (-SkipRust)'
}

# ------------------------------------------------------------------- Python
Write-Step 'Preparando el entorno virtual (.venv)'
if (-not (Test-Path $VenvPython)) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Stop-Bootstrap @'
No se encontró 'python'. Instala Python 3.11 o superior:

  winget install Python.Python.3.12
  # o https://www.python.org/downloads/
'@
    }

    & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        Stop-Bootstrap "Se requiere Python 3.11 o superior. La versión encontrada es inferior."
    }

    Invoke-Checked 'python' @('-m', 'venv', $Venv) 'No se pudo crear el entorno virtual (.venv)'
    Write-Ok 'entorno virtual creado'
} else {
    Write-Ok 'entorno virtual existente (se reutiliza)'
}

$versionPython = & $VenvPython -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
if ($LASTEXITCODE -ne 0) { Stop-Bootstrap "El intérprete de .venv no responde: borra .venv y vuelve a ejecutar." }
Write-Ok "Python $versionPython"

# -------------------------------------------------------------- dependencias
Write-Step 'Instalando dependencias (runtime + dev)'
Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--quiet', '--upgrade', 'pip') 'No se pudo actualizar pip'
Invoke-Checked $VenvPython @(
    '-m', 'pip', 'install', '--quiet',
    '-r', (Join-Path $Root 'requirements.txt'),
    '-r', (Join-Path $Root 'requirements-dev.txt')
) 'No se pudieron instalar las dependencias; revisa la conexión o el índice de paquetes'
Write-Ok 'dependencias al día'

Write-Step 'Instalando el proyecto en modo editable (nunca compila Rust)'
Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--quiet', '-e', $Root) 'Falló "pip install -e ."; revisa pyproject.toml'
Write-Ok 'paquetes app y py_bridge enlazados'

# ------------------------------------------------------- extensión nativa
Write-Step 'Comprobando la extensión nativa core_rust'
if ($AllowForwardAbi) {
    $env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY = '1'
    Write-Info 'PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 para esta ejecución'
}

$sitePackages = Join-Path $Venv 'Lib\site-packages'
if (-not (Test-Path $sitePackages)) {
    Stop-Bootstrap "No se encontró '$sitePackages'; el entorno virtual parece incompleto. Borra .venv y vuelve a ejecutar."
}
$instalado = Join-Path $sitePackages 'core_rust'
$artefacto = $null
if (Test-Path $instalado) {
    $artefacto = Get-ChildItem $instalado -File |
        Where-Object { $_.Name -like 'core_rust*' -and $_.Extension -in '.pyd', '.so', '.dylib' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

$fuentes = @(Get-ChildItem (Join-Path $Root 'core_rust\src') -Recurse -File)
$fuentes += Get-Item (Join-Path $Root 'core_rust\Cargo.toml')
$masReciente = ($fuentes | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime

$recompilar = $true
if ($null -ne $artefacto -and -not $Force -and $masReciente -le $artefacto.LastWriteTime) {
    $recompilar = $false
}

if (-not $recompilar) {
    Write-Ok "artefacto al día ($($artefacto.Name), $($artefacto.LastWriteTime.ToString('yyyy-MM-dd HH:mm')))"
    Write-Info 'se omite "maturin develop --release" (usa -Force para recompilar igualmente)'
} else {
    $maturin = $null
    if (Test-Path $VenvMaturin) {
        $maturin = $VenvMaturin
    } else {
        $enPath = Get-Command maturin -ErrorAction SilentlyContinue
        if ($enPath) { $maturin = $enPath.Source }
    }
    if (-not $maturin) {
        Stop-Bootstrap @'
No se encontró 'maturin'. Instálalo en el entorno virtual:

  .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
'@
    }

    Write-Info 'compilando con maturin develop --release (puede tardar varios minutos)...'
    Push-Location (Join-Path $Root 'core_rust')
    try {
        Invoke-Checked $maturin @('develop', '--release') @'
Falló "maturin develop --release". Causas habituales:

  - Falta el enlazador MSVC:
      winget install Microsoft.VisualStudio.2022.BuildTools
  - PyO3 no soporta este intérprete:
      vuelve a ejecutar con -AllowForwardAbi
'@
    } finally {
        Pop-Location
    }
    Write-Ok 'extensión nativa compilada e instalada'
}

Write-Step 'Verificando el núcleo nativo'
$versionNucleo = & $VenvPython -c "import core_rust; print(core_rust.version())"
if ($LASTEXITCODE -ne 0) {
    Stop-Bootstrap @'
La extensión nativa no se puede importar. Prueba:

  .\.venv\Scripts\python.exe -c "import core_rust"
  cd core_rust; ..\.venv\Scripts\maturin.exe develop --release

Si el intérprete es más nuevo que el abi3 de PyO3, usa -AllowForwardAbi.
'@
}
Write-Ok "núcleo $($versionNucleo.Trim())"

Write-Host ""
Write-Host "Entorno listo. Actívalo con:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "y arranca la aplicación con:" -ForegroundColor Green
Write-Host "  python -m app.main"

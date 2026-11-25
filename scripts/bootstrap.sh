#!/usr/bin/env bash
#
# Rig Studio — bootstrap idempotente del entorno (Linux / macOS / CI).
#
# Crea o reutiliza `.venv`, valida las versiones mínimas (Python 3.11+,
# rustc >= 1.88), instala dependencias y el proyecto en modo editable, y
# compila la extensión nativa solo si el artefacto instalado es más antiguo
# que core_rust/src (o si no existe).
#
# Uso:
#   scripts/bootstrap.sh [--allow-forward-abi] [--skip-rust] [--force]
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
MATURIN="$VENV/bin/maturin"

ALLOW_FORWARD_ABI=0
SKIP_RUST=0
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --allow-forward-abi) ALLOW_FORWARD_ABI=1 ;;
    --skip-rust) SKIP_RUST=1 ;;
    --force) FORCE=1 ;;
    -h | --help)
      sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "[ERROR] opción desconocida: $arg" >&2
      exit 1
      ;;
  esac
done

step() { printf '\n==> %s\n' "$1"; }
ok() { printf '    OK  %s\n' "$1"; }
info() { printf '        %s\n' "$1"; }
fail() {
  printf '\n[ERROR] %s\n' "$1" >&2
  exit 1
}

printf 'Rig Studio — bootstrap del entorno de desarrollo\n'
info "raíz del proyecto: $ROOT"

# --------------------------------------------------------------------- Rust
if [ "$SKIP_RUST" -eq 0 ]; then
  step 'Comprobando el toolchain de Rust'
  if ! command -v rustc >/dev/null 2>&1; then
    fail "No se encontró 'rustc'. Instálalo con:
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  # o:  winget install Rustlang.Rustup

Puedes omitir esta comprobación con --skip-rust."
  fi

  RUSTC_INFO="$(rustc -vV)"
  RELEASE="$(printf '%s\n' "$RUSTC_INFO" | awk '/^release: /{print $2}')"
  HOST="$(printf '%s\n' "$RUSTC_INFO" | awk '/^host: /{print $2}')"
  [ -n "$RELEASE" ] || fail "No se pudo interpretar la salida de 'rustc -vV'."

  if [ "$(printf '%s\n1.88\n' "$RELEASE" | sort -V | head -n1)" != "1.88" ]; then
    fail "rustc $RELEASE es anterior a la versión mínima 1.88 (RF-03/CA-04).

Actualiza el toolchain:
  rustup update stable"
  fi
  ok "rustc $RELEASE ($HOST)"
else
  info 'comprobación de Rust omitida (--skip-rust)'
fi

# ------------------------------------------------------------------- Python
step 'Preparando el entorno virtual (.venv)'
if [ ! -x "$PY" ]; then
  PY_BOOT=""
  for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY_BOOT="$candidate"
      break
    fi
  done
  [ -n "$PY_BOOT" ] || fail "No se encontró Python. Instala Python 3.11 o superior:
  sudo apt install python3 python3-venv      # Debian/Ubuntu
  brew install python@3.12                   # macOS"

  "$PY_BOOT" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' ||
    fail "Se requiere Python 3.11 o superior ($("$PY_BOOT" --version 2>&1) no sirve)."

  "$PY_BOOT" -m venv "$VENV" ||
    fail "No se pudo crear el entorno virtual. En Debian/Ubuntu instala:
  sudo apt install python3-venv"
  ok 'entorno virtual creado'
else
  ok 'entorno virtual existente (se reutiliza)'
fi

ok "Python $("$PY" -c "import sys; print('%d.%d.%d' % sys.version_info[:3])")"

# -------------------------------------------------------------- dependencias
step 'Instalando dependencias (runtime + dev)'
"$PY" -m pip install --quiet --upgrade pip || fail 'No se pudo actualizar pip'
"$PY" -m pip install --quiet \
  -r "$ROOT/requirements.txt" \
  -r "$ROOT/requirements-dev.txt" ||
  fail 'No se pudieron instalar las dependencias; revisa la conexión o el índice de paquetes'
ok 'dependencias al día'

step 'Instalando el proyecto en modo editable (nunca compila Rust)'
"$PY" -m pip install --quiet -e "$ROOT" || fail 'Falló "pip install -e ."; revisa pyproject.toml'
ok 'paquetes app y py_bridge enlazados'

# ------------------------------------------------------- extensión nativa
step 'Comprobando la extensión nativa core_rust'
if [ "$ALLOW_FORWARD_ABI" -eq 1 ]; then
  export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
  info 'PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 para esta ejecución'
fi

SITE_PACKAGES="$("$PY" -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")"
ARTIFACT="$(ls -t "$SITE_PACKAGES"/core_rust/core_rust.* 2>/dev/null | head -n1 || true)"

NEEDS_BUILD=1
if [ "$FORCE" -eq 0 ] && [ -n "$ARTIFACT" ] && [ -f "$ARTIFACT" ]; then
  # Idempotencia real: solo se recompila si hay fuentes más nuevas que el artefacto.
  if [ -z "$(find "$ROOT/core_rust/src" "$ROOT/core_rust/Cargo.toml" -newer "$ARTIFACT" -print -quit 2>/dev/null)" ]; then
    NEEDS_BUILD=0
  fi
fi

if [ "$NEEDS_BUILD" -eq 0 ]; then
  ok "artefacto al día ($(basename "$ARTIFACT"))"
  info 'se omite "maturin develop --release" (usa --force para recompilar igualmente)'
else
  if [ ! -x "$MATURIN" ]; then
    MATURIN="$(command -v maturin || true)"
  fi
  [ -n "$MATURIN" ] || fail "No se encontró 'maturin'. Instálalo con:
  \"$PY\" -m pip install -r requirements-dev.txt"

  info 'compilando con maturin develop --release (puede tardar varios minutos)...'
  (
    cd "$ROOT/core_rust"
    "$MATURIN" develop --release
  ) || fail "Falló 'maturin develop --release'. Causas habituales:
  - Falta un compilador de C (build-essential / Xcode Command Line Tools)
  - PyO3 no soporta este intérprete: vuelve a ejecutar con --allow-forward-abi"
  ok 'extensión nativa compilada e instalada'
fi

step 'Verificando el núcleo nativo'
"$PY" -c "import core_rust; print('    núcleo', core_rust.version())" || fail "La extensión nativa no se puede importar. Prueba:
  \"$PY\" -c \"import core_rust\"
  cd core_rust && \"$MATURIN\" develop --release"

printf '\nEntorno listo. Actívalo con:\n'
printf '  source .venv/bin/activate\n'
printf 'y arranca la aplicación con:\n'
printf '  python -m app.main\n'

"""Carga de la extensión nativa `core_rust` y diagnóstico del núcleo.

Estrategia de búsqueda (en orden):
1. `import core_rust` normal (caso `maturin develop` / wheel instalado).
2. `core_rust/target/release` y `core_rust/target/debug` (caso `cargo build`),
   copiando el artefacto a `py_bridge/_native/` con el nombre importable.
3. `py_bridge/_native` (copias manuales del .pyd/.so).

Trampa importante: el directorio `core_rust/` de la raíz del proyecto **sombra**
al módulo compilado. Desde la raíz, `import core_rust` devuelve un *namespace
package* vacío (sin `version`, sin `__version__`) y Python no lanza ImportError.
Por eso toda importación se valida con `_is_valid()` y, si es un namespace
vacío, se purga de `sys.modules` antes de seguir buscando.

Además de cargar el módulo, esta capa ofrece un diagnóstico que **nunca lanza**
(:func:`core_status`), pensado para la UI: distingue «no hay artefacto» de
«existe pero no se pudo cargar» y avisa si el proyecto declara una versión más
nueva que la compilada (RF-07 / CA-08).
"""

from __future__ import annotations

import importlib
import shutil
import sys
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_NATIVE_DIR = Path(__file__).resolve().parent / "_native"

#: Directorios donde cargo/maturin dejan artefactos sin instalar.
_BUILD_DIRS: tuple[Path, ...] = (
    _PROJECT_ROOT / "core_rust" / "target" / "release",
    _PROJECT_ROOT / "core_rust" / "target" / "debug",
)

_MANIFEST = _PROJECT_ROOT / "core_rust" / "Cargo.toml"

_MODULE = "core_rust"

#: Artefacto producido por cargo -> nombre que Python sí puede importar.
#: (Python solo carga `.pyd` en Windows y `<módulo>.so` en Linux/macOS.)
_ARTIFACT_NAMES: dict[str, str] = {
    "core_rust.pyd": "core_rust.pyd",
    "core_rust.dll": "core_rust.pyd",
    "core_rust.so": "core_rust.so",
    "libcore_rust.so": "core_rust.so",
    "core_rust.dylib": "core_rust.so",
    "libcore_rust.dylib": "core_rust.so",
}

_HINT_NOT_FOUND = """\
La extensión nativa 'core_rust' no está disponible. Compílala con una de estas opciones:

  # Opción A (recomendada): instalarla en el entorno virtual activo
  cd core_rust
  maturin develop --release

  # Opción B: construir un wheel e instalarlo
  cd core_rust
  maturin build --release
  pip install --force-reinstall target/wheels/core_rust-*.whl

  # Opción C: compilar en crudo; py_bridge renombra el artefacto automáticamente
  cd core_rust
  cargo build --release
"""

_HINT_LOAD_FAILED = """\
La extensión nativa 'core_rust' existe pero no se pudo cargar: {motivo}

Causas habituales:

  # 1. El intérprete es más nuevo que el abi3 soportado por PyO3
  #    (compila con compatibilidad hacia delante):
  $env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY = "1"      # PowerShell
  export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1        # bash
  cd core_rust; maturin develop --release

  # 2. El artefacto está corrupto o se mezcló con otra versión de Python:
  cd core_rust; maturin develop --release
"""


class CoreNotBuiltError(ImportError):
    """El módulo nativo no existe o no se pudo cargar."""


@dataclass(frozen=True, slots=True)
class CoreStatus:
    """Diagnóstico del núcleo listo para la UI (RF-04, RF-07).

    `detail` es el texto en español que se puede mostrar tal cual:
    ``núcleo 0.1.0``, ``núcleo no disponible: <motivo>`` o
    ``núcleo 0.1.0 (el proyecto declara 0.2.0; recompila con maturin develop --release)``.
    """

    available: bool
    loaded_version: str | None
    expected_version: str | None
    stale: bool
    detail: str


_cached: ModuleType | None = None


def _is_valid(module: ModuleType | None) -> bool:
    """True si el módulo es la extensión real (y no un namespace package vacío)."""
    return module is not None and hasattr(module, "version") and hasattr(module, "__version__")


def _purge_shadow() -> None:
    """Elimina de `sys.modules` cualquier `core_rust` inválido (namespace vacío)."""
    current = sys.modules.get(_MODULE)
    if current is not None and not _is_valid(current):
        del sys.modules[_MODULE]


def _intentar_importar() -> tuple[ModuleType | None, str, bool]:
    """Intenta importar la extensión.

    Devuelve ``(módulo, motivo, había_candidato)``: ``motivo`` explica el fallo
    y ``había_candidato`` es cierto cuando el import **encontró** algo que no se
    pudo usar (artefacto incompatible o namespace vacío), lo que permite dar un
    mensaje distinto al de «no hay nada compilado».
    """
    _purge_shadow()
    try:
        importlib.invalidate_caches()
        module = importlib.import_module(_MODULE)
    except ModuleNotFoundError:
        return None, "no se encontró una extensión importable", False
    except ImportError as exc:  # p. ej. falta Visual C++ Redistributable
        return None, f"el import falló ({exc})", True
    except OSError as exc:  # artefacto de otra arquitectura o corrupto
        return None, f"{exc}", True
    if not _is_valid(module):
        _purge_shadow()
        return (
            None,
            "el import devolvió un paquete vacío (el directorio core_rust/ de la raíz "
            "sombra al módulo compilado)",
            True,
        )
    return module, "", False


def _try_import() -> ModuleType | None:
    """Versión mínima de `_intentar_importar` (sin diagnóstico)."""
    return _intentar_importar()[0]


def _materialize_artifacts() -> tuple[bool, Path | None]:
    """Copia el artefacto de cargo a `_native/` con el nombre importable.

    No sobrescribe un binario cargado por el proceso: solo copia si el destino
    no existe o si el origen es más reciente. Devuelve ``(disponible, origen)``,
    donde `origen` es el artefacto más reciente encontrado en un directorio de
    compilación (``None`` si no hay ninguno).
    """
    copied = False
    newest_source: Path | None = None
    for build_dir in _BUILD_DIRS:
        if not build_dir.is_dir():
            continue
        for source_name, target_name in _ARTIFACT_NAMES.items():
            source = build_dir / source_name
            if not source.is_file():
                continue
            if newest_source is None or source.stat().st_mtime > newest_source.stat().st_mtime:
                newest_source = source
            target = _NATIVE_DIR / target_name
            if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
                copied = True
                continue
            try:
                _NATIVE_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied = True
            except OSError:
                # Windows no permite sobrescribir un .pyd en uso: se ignora.
                copied = copied or target.is_file()
    return copied, newest_source


def _artefacto_disponible() -> Path | None:
    """Primer artefacto nativo que existe en los directorios de búsqueda, si hay."""
    for directory in (*_BUILD_DIRS, _NATIVE_DIR):
        if not directory.is_dir():
            continue
        for name in _ARTIFACT_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def _resolver(force_reload: bool = False) -> tuple[ModuleType | None, str, bool]:
    """Resuelve la extensión y la deja en caché. No lanza `CoreNotBuiltError`."""
    global _cached  # noqa: PLW0603 - caché de módulo deliberada

    if _cached is not None and not force_reload:
        return _cached, "", False
    if force_reload:
        _cached = None
        _purge_shadow()

    module, motivo, existia = _intentar_importar()
    if module is None:
        copiado, origen = _materialize_artifacts()
        for directory in (*_BUILD_DIRS, _NATIVE_DIR):
            if directory.is_dir():
                resolved = str(directory)
                if resolved not in sys.path:
                    sys.path.insert(0, resolved)
        module, motivo, existia_tras_copiar = _intentar_importar()
        existia = existia or existia_tras_copiar or copiado or origen is not None

    if module is None:
        if _artefacto_disponible() is not None:
            existia = True
        return None, motivo, existia

    _cached = module
    return module, "", existia


def load_core(force_reload: bool = False) -> ModuleType:
    """Devuelve el módulo nativo `core_rust` o lanza `CoreNotBuiltError`."""
    module, motivo, existia = _resolver(force_reload)
    if module is None:
        raise CoreNotBuiltError(
            _HINT_LOAD_FAILED.format(motivo=motivo) if existia else _HINT_NOT_FOUND
        )
    return module


def core() -> ModuleType:
    """Alias corto de `load_core()` para usar en la UI."""
    return load_core()


def core_version() -> str:
    """Versión del núcleo nativo, o 'no disponible' si no está compilado."""
    try:
        return str(load_core().version())
    except (CoreNotBuiltError, AttributeError):
        return "no disponible"


@lru_cache(maxsize=1)
def expected_core_version() -> str | None:
    """Versión declarada en `core_rust/Cargo.toml`, o `None` si no se puede leer.

    El resultado se cachea porque el manifiesto no cambia durante la vida del
    proceso; las pruebas pueden limpiar la caché con
    ``expected_core_version.cache_clear()``.
    """
    try:
        with _MANIFEST.open("rb") as archivo:
            datos = tomllib.load(archivo)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    paquete = datos.get("package")
    if not isinstance(paquete, dict):
        return None
    version = paquete.get("version")
    return version if isinstance(version, str) else None


def core_status() -> CoreStatus:
    """Diagnóstico completo del núcleo; **nunca** lanza (RF-07 / CA-08)."""
    declarada = expected_core_version()
    module, motivo, _ = _resolver()

    if module is None:
        return CoreStatus(
            available=False,
            loaded_version=None,
            expected_version=declarada,
            stale=False,
            detail=f"núcleo no disponible: {motivo or 'no se pudo cargar'}",
        )

    try:
        cargada: str | None = str(module.version())
    except Exception:  # noqa: BLE001 - un diagnóstico no debe romper la UI
        cargada = "desconocida"

    stale = declarada is not None and cargada != declarada
    if stale:
        detail = (
            f"núcleo {cargada} (el proyecto declara {declarada}; "
            "recompila con maturin develop --release)"
        )
    else:
        detail = f"núcleo {cargada}"

    return CoreStatus(
        available=True,
        loaded_version=cargada,
        expected_version=declarada,
        stale=stale,
        detail=detail,
    )

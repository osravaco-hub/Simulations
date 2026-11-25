"""Carga y diagnóstico del núcleo nativo (`py_bridge/native.py`, T08).

Cubre los dos modos de fallo que la UI debe distinguir (RF-07 / CA-08) —«no hay
artefacto» y «existe pero no se pudo cargar»—, la purga del *namespace* vacío
que crea el directorio `core_rust/` de la raíz, la materialización del artefacto
de cargo y el aviso de versión desactualizada.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from py_bridge import native


class _ImportadorRoto:
    """Sustituto de `importlib` que simula «no hay extensión instalada»."""

    @staticmethod
    def invalidate_caches() -> None:
        return None

    @staticmethod
    def import_module(name: str) -> ModuleType:
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)


def _nombre_de_cargo() -> str:
    """Nombre que deja `cargo build` para la cdylib en esta plataforma."""
    if os.name == "nt":
        return "core_rust.dll"
    if sys.platform.startswith("linux"):
        return "libcore_rust.so"
    return "libcore_rust.dylib"


@pytest.fixture(autouse=True)
def _aislar_estado(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ni caché de módulo ni caché de versión sobreviven entre pruebas.

    La caché se limpia **antes** de cada prueba: después no se puede tocar, porque
    `expected_core_version` puede estar sustituida por un doble y `monkeypatch`
    aún no ha restaurado el original al desmontar esta fixture.
    """
    monkeypatch.setattr(native, "_cached", None)
    native.expected_core_version.cache_clear()
    yield


def test_version_sin_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin artefacto: `core_version()` no lanza y el error nombra las tres vías."""
    monkeypatch.setattr(native, "_BUILD_DIRS", ())
    monkeypatch.setattr(native, "_NATIVE_DIR", tmp_path / "nativa")
    monkeypatch.setattr(native, "importlib", _ImportadorRoto)

    assert native.core_version() == "no disponible"

    with pytest.raises(native.CoreNotBuiltError) as error:
        native.load_core()
    mensaje = str(error.value)
    for pista in ("maturin develop --release", "maturin build --release", "cargo build --release"):
        assert pista in mensaje

    estado = native.core_status()
    assert estado.available is False
    assert estado.loaded_version is None
    assert estado.stale is False
    assert estado.detail.startswith("núcleo no disponible: ")


@pytest.mark.native
def test_import_desde_otro_directorio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """La resolución no depende del directorio de trabajo (mata la trampa del namespace)."""
    monkeypatch.chdir(tmp_path)

    modulo = native.load_core(force_reload=True)

    assert Path(modulo.__file__).resolve().is_file()
    assert isinstance(modulo.version(), str) and modulo.version()


@pytest.mark.native
def test_purga_namespace_vacio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un `core_rust` sin `version()` en `sys.modules` se descarta y se sigue buscando."""
    falso = ModuleType("core_rust")
    monkeypatch.setitem(sys.modules, "core_rust", falso)
    # El paquete instalado reejecuta su `__init__.py`; hay que simular un proceso
    # limpio para que `from .core_rust import *` vuelva a enlazar el submódulo.
    for clave in [k for k in sys.modules if k.startswith("core_rust.")]:
        monkeypatch.delitem(sys.modules, clave, raising=False)

    modulo = native.load_core(force_reload=True)

    assert modulo is not falso
    assert hasattr(modulo, "version")
    assert sys.modules["core_rust"] is modulo


def test_no_cachea_modulo_invalido(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un fallo de resolución no deja un módulo inválido en la caché."""
    monkeypatch.setattr(native, "_BUILD_DIRS", ())
    monkeypatch.setattr(native, "_NATIVE_DIR", tmp_path / "nativa")
    monkeypatch.setattr(native, "importlib", _ImportadorRoto)

    with pytest.raises(native.CoreNotBuiltError):
        native.load_core()

    assert native._cached is None
    estado = native.core_status()
    assert estado.available is False
    assert "no se encontró" in estado.detail


def test_materializa_artefacto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`cargo build` deja el artefacto crudo; py_bridge lo copia con nombre importable."""
    nombre_cargo = _nombre_de_cargo()
    compilado = tmp_path / "target" / "release"
    compilado.mkdir(parents=True)
    origen = compilado / nombre_cargo
    origen.write_bytes(b"artefacto-de-prueba")
    destino = tmp_path / "nativa"
    monkeypatch.setattr(native, "_BUILD_DIRS", (compilado,))
    monkeypatch.setattr(native, "_NATIVE_DIR", destino)

    disponible, fuente = native._materialize_artifacts()

    assert disponible is True
    assert fuente == origen
    copia = destino / native._ARTIFACT_NAMES[nombre_cargo]
    assert copia.read_bytes() == b"artefacto-de-prueba"

    # Idempotencia: la segunda pasada no reescribe el destino.
    antes = copia.stat().st_mtime
    disponible_otra_vez, fuente_otra_vez = native._materialize_artifacts()
    assert disponible_otra_vez is True
    assert fuente_otra_vez == origen
    assert copia.stat().st_mtime == antes

    # Sin artefactos en ningún directorio: ni copia ni origen.
    monkeypatch.setattr(native, "_BUILD_DIRS", (tmp_path / "vacio",))
    assert native._materialize_artifacts() == (False, None)


@pytest.mark.native
def test_tres_vias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Las tres ubicaciones de búsqueda entregan un módulo importable.

    1. Instalada (`site-packages`, vía `maturin develop`).
    2./3. Artefacto en un directorio de compilación materializado en `_native/`,
       que se importa en un subproceso con solo `PYTHONPATH` apuntando allí.
    """
    instalada = native.load_core()
    ruta_instalada = Path(instalada.__file__).resolve()
    assert ruta_instalada.is_file()

    extension = next(
        archivo
        for archivo in ruta_instalada.parent.iterdir()
        if archivo.suffix in {".pyd", ".so", ".dylib"}
    )

    nombre_cargo = _nombre_de_cargo()
    compilado = tmp_path / "target" / "release"
    compilado.mkdir(parents=True)
    shutil.copy2(extension, compilado / nombre_cargo)
    destino = tmp_path / "nativa"
    monkeypatch.setattr(native, "_BUILD_DIRS", (compilado,))
    monkeypatch.setattr(native, "_NATIVE_DIR", destino)

    disponible, fuente = native._materialize_artifacts()
    copia = destino / native._ARTIFACT_NAMES[nombre_cargo]
    assert disponible is True
    assert fuente == compilado / nombre_cargo
    assert copia.is_file()

    entorno = {**os.environ, "PYTHONPATH": str(destino)}
    proceso = subprocess.run(
        [sys.executable, "-c", "import core_rust; print(core_rust.version())"],
        cwd=tmp_path,
        env=entorno,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proceso.returncode == 0, proceso.stderr
    assert proceso.stdout.strip() == instalada.version()


def test_expected_core_version_lee_el_manifiesto() -> None:
    """La versión declarada sale de `core_rust/Cargo.toml` con `tomllib`."""
    with native._MANIFEST.open("rb") as archivo:
        declarada = tomllib.load(archivo)["package"]["version"]

    assert native.expected_core_version() == declarada
    assert native.expected_core_version() == declarada  # cacheada


def test_expected_core_version_sin_manifiesto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un manifiesto ilegible devuelve `None` en lugar de lanzar."""
    monkeypatch.setattr(native, "_MANIFEST", tmp_path / "no-existe.toml")
    native.expected_core_version.cache_clear()

    assert native.expected_core_version() is None


@pytest.mark.native
def test_core_status_actualizado() -> None:
    """Núcleo y proyecto coinciden: sin aviso y texto corto."""
    estado = native.core_status()

    assert estado.available is True
    assert estado.stale is False
    assert estado.loaded_version == native.core_version()
    assert estado.detail == f"núcleo {estado.loaded_version}"


@pytest.mark.native
def test_core_status_desactualizado(monkeypatch: pytest.MonkeyPatch) -> None:
    """El proyecto declara otra versión: `stale` y aviso accionable (CA-08)."""
    monkeypatch.setattr(native, "expected_core_version", lambda: "9.9.9")

    estado = native.core_status()

    assert estado.available is True
    assert estado.expected_version == "9.9.9"
    assert estado.stale is True
    assert estado.loaded_version != "9.9.9"
    assert "el proyecto declara 9.9.9" in estado.detail
    assert "maturin develop --release" in estado.detail

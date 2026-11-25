"""Estructura del bootstrap y de la configuración del proyecto (T03–T07).

No ejecuta los scripts (el `.ps1` compila y el `.sh` es para CI); comprueba que
existen, que son idempotentes **por construcción** y que el reparto de
dependencias y la configuración de herramientas respetan el diseño.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"
PS1 = SCRIPTS / "bootstrap.ps1"
SH = SCRIPTS / "bootstrap.sh"


def _texto(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8-sig")


def test_scripts_de_bootstrap_existen() -> None:
    assert PS1.is_file(), "falta scripts/bootstrap.ps1"
    assert SH.is_file(), "falta scripts/bootstrap.sh"
    assert _texto(SH).startswith("#!/usr/bin/env bash")


def test_ps1_no_reinstala_ni_recompila_a_ciegas() -> None:
    """Idempotencia por estructura: reutiliza el venv y compara marcas de tiempo."""
    texto = _texto(PS1)

    # Reutiliza el entorno si ya existe.
    assert "Test-Path $VenvPython" in texto
    # Solo compila si las fuentes son más nuevas que el artefacto instalado.
    assert "LastWriteTime" in texto
    assert "maturin" in texto and "-Force" in texto
    # Nunca destruye el entorno ni el proyecto.
    assert not re.search(r"Remove-Item[^\n]*-Recurse", texto)
    # Mensajes accionables y salida anticipada en lugar de trazas de PowerShell.
    assert "winget install Rustlang.Rustup" in texto
    assert "exit 1" in texto
    # Compatibilidad hacia delante de PyO3 disponible por bandera.
    assert "-AllowForwardAbi" in texto
    assert "PYO3_USE_ABI3_FORWARD_COMPATIBILITY" in texto


def test_sh_es_idempotente_y_analiza_sintacticamente() -> None:
    texto = _texto(SH)

    assert "set -euo pipefail" in texto
    assert "--force" in texto
    assert "-newer" in texto and "maturin" in texto
    assert "PYO3_USE_ABI3_FORWARD_COMPATIBILITY" in texto
    assert "winget install Rustlang.Rustup" in texto

    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - depende del entorno
        pytest.skip("bash no está disponible para comprobar la sintaxis")
    resultado = subprocess.run(
        [bash, "-n", str(SH)], capture_output=True, text=True, check=False
    )
    assert resultado.returncode == 0, resultado.stderr


def _dependencias(ruta: Path) -> list[str]:
    """Líneas de dependencia efectivas (sin comentarios ni líneas vacías)."""
    efectivas = []
    for linea in _texto(ruta).splitlines():
        limpia = linea.split("#", 1)[0].strip().lower()
        if limpia:
            efectivas.append(limpia)
    return efectivas


def test_requirements_separan_runtime_dev_y_ml() -> None:
    """RF-02/RF-29: torch y las herramientas de desarrollo no están en runtime (D-15)."""
    runtime = _dependencias(RAIZ / "requirements.txt")
    dev = _dependencias(RAIZ / "requirements-dev.txt")
    ml = _dependencias(RAIZ / "requirements-ml.txt")

    assert not [linea for linea in runtime if linea.startswith(("torch", "maturin"))]
    assert any(linea.startswith("pyside6") for linea in runtime)
    assert any(linea.startswith("numpy") for linea in runtime)

    assert any(linea.startswith("torch") for linea in ml)
    assert "cu124" in _texto(RAIZ / "requirements-ml.txt")  # comentario con los índices CUDA

    for herramienta in ("pytest", "pytest-qt", "jsonschema", "ruff", "maturin"):
        assert any(linea.startswith(herramienta) for linea in dev), (
            f"falta {herramienta} en requirements-dev.txt"
        )


def test_manifiesto_raiz_no_compila_rust() -> None:
    """D-10: `pip install -e .` instala solo los paquetes Python."""
    texto = _texto(RAIZ / "pyproject.toml")

    assert 'build-backend = "setuptools.build_meta"' in texto
    assert 'requires = ["setuptools>=68"]' in texto
    assert 'packages = ["app", "py_bridge"]' in texto

    dependencias = texto.split("dependencies = [", 1)[1].split("]", 1)[0].lower()
    assert "maturin" not in dependencias
    assert "torch" not in dependencias

    for marcador in ('"gui:', '"native:', '"slow:'):
        assert marcador in texto, f"falta el marcador {marcador} en pyproject.toml"


def test_workflow_de_ci_cubre_ambas_plataformas() -> None:
    """RF-28/CA-30: matriz Windows/Linux con formato, clippy, pruebas y lint."""
    flujo = _texto(RAIZ / ".github" / "workflows" / "ci.yml")

    for patron in (
        "windows-latest",
        "ubuntu-latest",
        "cargo fmt",
        "cargo clippy",
        "cargo test --no-default-features",
        "pytest",
        "ruff check",
    ):
        assert patron in flujo, f"el workflow no incluye «{patron}»"
    assert "QT_QPA_PLATFORM" in flujo


def test_gitignore_cubre_los_artefactos_generados() -> None:
    texto = _texto(RAIZ / ".gitignore")

    for patron in (
        "core_rust/target/",
        "py_bridge/_native/",
        ".ruff_cache/",
        ".mypy_cache/",
        "*.egg-info/",
        "htmlcov/",
        ".venv/",
    ):
        assert patron in texto, f"falta «{patron}» en .gitignore"

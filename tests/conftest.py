"""Fixtures compartidas de la suite de pruebas de Rig Studio.

`tests/conftest.py` es parte del arnés mínimo (T07): centraliza las fixtures
geométricas del contrato de escena, el acceso a `tests/fixtures/` y las fixtures
que dependen de la extensión nativa o de Qt, de modo que la suite rápida
(`pytest -m "not gui"`) se pueda ejecutar sin toolchain Rust ni servidor gráfico.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from py_bridge.scene import Scene, scene_from_numpy

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
PROJECT_ROOT = TESTS_DIR.parent

#: Vértices del cubo unitario centrado en el origen (diseño §3.5).
CUBO_VERTICES: tuple[float, ...] = (
    -0.5,
    -0.5,
    -0.5,
    0.5,
    -0.5,
    -0.5,
    0.5,
    0.5,
    -0.5,
    -0.5,
    0.5,
    -0.5,
    -0.5,
    -0.5,
    0.5,
    0.5,
    -0.5,
    0.5,
    0.5,
    0.5,
    0.5,
    -0.5,
    0.5,
    0.5,
)

#: Triángulos del cubo (12 caras, índices en [0, 8)).
CUBO_FACES: tuple[int, ...] = (
    0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
    1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7,
)

#: Articulaciones del esqueleto de ejemplo (5 articulaciones, diseño §3.5).
ESQUELETO_JOINTS: tuple[float, ...] = (
    0.0,
    -0.5,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.5,
    0.0,
    0.35,
    0.5,
    0.0,
    -0.35,
    0.5,
    0.0,
)

ESQUELETO_PARENTS: tuple[int, ...] = (-1, 0, 1, 2, 2)
ESQUELETO_NAMES: tuple[str, ...] = ("root", "spine", "head", "arm_l", "arm_r")


def cubo_arrays() -> tuple[np.ndarray, np.ndarray]:
    """Devuelve ``(vertices (8,3) float32, faces (12,3) int32)`` del cubo de ejemplo."""
    vertices = np.array(CUBO_VERTICES, dtype=np.float32).reshape(8, 3)
    faces = np.array(CUBO_FACES, dtype=np.int32).reshape(12, 3)
    return vertices, faces


def esqueleto_arrays() -> np.ndarray:
    """Devuelve ``joints (5,3) float32`` del esqueleto de ejemplo."""
    return np.array(ESQUELETO_JOINTS, dtype=np.float32).reshape(5, 3)


def escena_de_ejemplo() -> Scene:
    """Escena cubo + esqueleto de 5 articulaciones con metadatos de ejemplo."""
    vertices, faces = cubo_arrays()
    return scene_from_numpy(
        "cubo",
        vertices,
        faces,
        joints=esqueleto_arrays(),
        parents=ESQUELETO_PARENTS,
        joint_names=ESQUELETO_NAMES,
        metadata={"source": "example://cube", "units": "m"},
    )


@pytest.fixture()
def fixtures_dir() -> Path:
    """Ruta del directorio de fixtures del contrato de escena."""
    return FIXTURES_DIR


@pytest.fixture()
def cubo() -> tuple[np.ndarray, np.ndarray]:
    """Cubo unitario de 8 vértices y 12 caras, en los dtypes del contrato."""
    return cubo_arrays()


@pytest.fixture()
def escena() -> Scene:
    """Escena cubo + esqueleto lista para serializar o validar."""
    return escena_de_ejemplo()


@pytest.fixture(scope="session")
def core() -> Any:
    """Extensión nativa ``core_rust``; la prueba se salta si no está compilada."""
    from py_bridge.native import CoreNotBuiltError, load_core

    try:
        return load_core()
    except CoreNotBuiltError as exc:  # pragma: no cover - depende del entorno
        pytest.skip(f"extensión nativa no disponible: {exc}")


@pytest.fixture(scope="session")
def qapp() -> Iterator[Any]:
    """``QApplication`` para pruebas marcadas ``gui``.

    No se crea ninguna ventana; sólo se garantiza la instancia única. Las pruebas
    que necesiten interacción con widgets usarán ``qtbot`` (pytest-qt) cuando esa
    dependencia esté instalada (Fase 3).
    """
    pytest.importorskip("PySide6", reason="PySide6 no está instalado")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    creada = app is None
    if app is None:  # pragma: no cover - depende del entorno
        app = QApplication([])
    yield app
    if creada:  # pragma: no cover - depende del entorno
        app.quit()

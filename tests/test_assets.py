"""Activos de ejemplo ``assets/meshes/*.scene.json`` (T19, E-05, E-07).

Los documentos se generaron con ``Scene.to_json()`` y se versionan; estas
pruebas comprueban que cargan, que los conteos son los esperados, que los huesos
se derivan de ``parents`` y que el archivo es exactamente la serialización
canónica (no una copia editada a mano).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from py_bridge.scene import load_scene_file

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "meshes"

CUBO = ASSETS / "example_cube.scene.json"
RIGGED = ASSETS / "example_rigged.scene.json"


@pytest.mark.parametrize("ruta", [CUBO, RIGGED], ids=["example_cube", "example_rigged"])
def test_el_activo_existe(ruta: Path) -> None:
    assert ruta.is_file()


def test_cubo_de_ejemplo() -> None:
    escena = load_scene_file(CUBO)

    assert escena.name == "cubo"
    assert escena.mesh is not None
    assert escena.mesh.vertex_count == 8
    assert escena.mesh.face_count == 12
    assert escena.skeleton is None


def test_escena_rigged_de_ejemplo() -> None:
    escena = load_scene_file(RIGGED)

    assert escena.name == "cubo_rigged"
    assert escena.mesh is not None
    assert escena.mesh.vertex_count == 8
    assert escena.mesh.face_count == 12

    esqueleto = escena.skeleton
    assert esqueleto is not None
    assert esqueleto.joint_count == 5
    assert len(esqueleto.bones) == 4
    assert esqueleto.parents == (-1, 0, 1, 2, 2)
    assert esqueleto.names == ("root", "spine", "head", "arm_l", "arm_r")
    assert esqueleto.bones == ((1, 0), (2, 1), (3, 2), (4, 2))


@pytest.mark.parametrize("ruta", [CUBO, RIGGED], ids=["example_cube", "example_rigged"])
def test_el_activo_es_la_serializacion_canonica(ruta: Path) -> None:
    texto = ruta.read_text(encoding="utf-8")

    assert texto == load_scene_file(ruta).to_json()
    assert not texto.endswith("\n")
    assert texto.startswith('{"schema_version":1,')

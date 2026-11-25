"""Determinismo de la serialización (RF-10, CA-10, RF-25).

Comprueba que la misma escena produce el mismo JSON byte a byte en dos procesos
con ``PYTHONHASHSEED`` distinto, que la conversión por trozos coincide con una
sola pasada y que el progreso es monótono y cancelable.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import py_bridge.scene as modulo_escena
from py_bridge.scene import Scene, mesh_from_numpy, to_json

RAIZ = Path(__file__).resolve().parents[1]

_SUBPROCESO = """
import hashlib

import numpy as np

from py_bridge.scene import scene_from_numpy

VERTICES = (-0.5, -0.5, -0.5, 0.5, -0.5, -0.5, 0.5, 0.5, -0.5, -0.5, 0.5, -0.5,
            -0.5, -0.5, 0.5, 0.5, -0.5, 0.5, 0.5, 0.5, 0.5, -0.5, 0.5, 0.5)
FACES = (0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
         1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7)
JOINTS = (0.0, -0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.35, 0.5, 0.0, -0.35, 0.5, 0.0)

escena = scene_from_numpy(
    "cubo",
    np.array(VERTICES, dtype=np.float32).reshape(8, 3),
    np.array(FACES, dtype=np.int32).reshape(12, 3),
    joints=np.array(JOINTS, dtype=np.float32).reshape(5, 3),
    parents=(-1, 0, 1, 2, 2),
    joint_names=("root", "spine", "head", "arm_l", "arm_r"),
    metadata={"units": "m", "source": "example://cube"},
)
documento = escena.to_json()
print(hashlib.sha256(documento.encode("utf-8")).hexdigest())
print(len(documento))
"""


def _ejecutar_subproceso(semilla: str) -> str:
    """Serializa la escena en un proceso nuevo y devuelve ``<sha256>\\n<longitud>``."""
    entorno = {**os.environ, "PYTHONHASHSEED": semilla, "PYTHONPATH": str(RAIZ)}
    proceso = subprocess.run(  # noqa: S603 - comando fijo construido en el test
        [sys.executable, "-c", _SUBPROCESO],
        cwd=RAIZ,
        env=entorno,
        capture_output=True,
        text=True,
        check=True,
    )
    return proceso.stdout.strip()


def test_dos_procesos_producen_el_mismo_documento() -> None:
    primera = _ejecutar_subproceso("0")
    segunda = _ejecutar_subproceso("12345")

    assert primera == segunda
    lineas = primera.splitlines()
    assert len(lineas) == 2
    assert len(lineas[0]) == 64
    assert int(lineas[1]) > 0


def test_el_hash_coincide_con_la_serializacion_local(escena: Scene) -> None:
    sha_local = hashlib.sha256(escena.to_json().encode("utf-8")).hexdigest()
    assert _ejecutar_subproceso("7").splitlines()[0] == sha_local


def test_troceado_produce_los_mismos_bytes(monkeypatch: pytest.MonkeyPatch, escena: Scene) -> None:
    monkeypatch.setattr(modulo_escena, "_CHUNK_ROWS", 2)
    completo = escena.to_json()

    fracciones: list[float] = []
    troceado = to_json(escena, progress=fracciones.append)

    assert troceado == completo
    assert len(fracciones) > 1


def test_la_escena_grande_coincide_con_su_troceado() -> None:
    filas = modulo_escena._CHUNK_ROWS + 3
    vertices = np.zeros((filas, 3), np.float32)
    malla = mesh_from_numpy(vertices, np.zeros((0, 3), np.int32))
    escena = Scene(mesh=malla, name="grande")

    fracciones: list[float] = []
    troceado = to_json(escena, progress=fracciones.append)

    assert troceado == escena.to_json()
    assert len(fracciones) >= 2


def test_fracciones_monotonas_y_completas(monkeypatch: pytest.MonkeyPatch, escena: Scene) -> None:
    monkeypatch.setattr(modulo_escena, "_CHUNK_ROWS", 2)
    fracciones: list[float] = []

    to_json(escena, progress=fracciones.append)

    assert fracciones
    assert fracciones[-1] == pytest.approx(1.0)
    assert all(0.0 <= fraccion <= 1.0 for fraccion in fracciones)
    assert all(
        segunda >= primera
        for primera, segunda in zip(fracciones, fracciones[1:], strict=False)
    )
    assert fracciones == sorted(set(fracciones))


def test_progreso_que_lanza_aborta_la_serializacion(escena: Scene) -> None:
    llamadas: list[float] = []

    def cancelar(fraccion: float) -> None:
        llamadas.append(fraccion)
        raise RuntimeError("cancelado por la prueba")

    with pytest.raises(RuntimeError):
        to_json(escena, progress=cancelar)

    assert llamadas
    assert llamadas[0] < 1.0


def test_progreso_sin_llamadas_extra_al_final(escena: Scene) -> None:
    fracciones: list[float] = []
    to_json(escena, progress=fracciones.append)
    assert fracciones[-1] == pytest.approx(1.0)
    assert fracciones.count(fracciones[-1]) == 1

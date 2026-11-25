"""Entradas no conformes: mensajes accionables y proceso intacto (T31).

Se prueban **las dos capas**, porque el contrato es distinto en cada una:

- `core_rust` (FFI) exige búferes exactos: dtype distinto o no contiguo es error.
  Sus mensajes incluyen el remedio (``np.ascontiguousarray``,
  ``faces.view(np.uint32)``).
- `py_bridge.geometry` **normaliza** antes de llamar (RF-09): acepta ``float64``
  o arreglos no contiguos y los convierte. Solo rechaza lo que no puede
  interpretar sin pérdida (dtype no numérico, forma incorrecta, negativos).

Ningún caso puede tumbar el proceso (E-12): al final se vuelve a llamar al
núcleo y debe responder.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from py_bridge import geometry

pytestmark = pytest.mark.native

VERTICES = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
CARAS = np.array([[0, 1, 2]], dtype=np.int32)


# --------------------------------------------------------------- núcleo (FFI)


@pytest.mark.parametrize(
    ("arreglo", "dtype"),
    [
        (np.zeros((4, 3), dtype=np.float64), "float64"),
        (np.zeros((4, 3), dtype=np.int32), "int32"),
    ],
)
def test_el_nucleo_rechaza_vertices_que_no_son_float32(
    core: Any, arreglo: np.ndarray, dtype: str
) -> None:
    with pytest.raises(TypeError) as error:
        core.bounds(arreglo)

    mensaje = str(error.value)
    assert "vertices" in mensaje
    assert "float32" in mensaje


@pytest.mark.parametrize(
    "vista",
    [
        pytest.param("transpuesta", id="transpuesta"),
        pytest.param("columnas", id="columnas"),
    ],
)
def test_el_nucleo_rechaza_buferes_no_contiguos(core: Any, vista: str) -> None:
    arreglo = np.zeros((4, 6), dtype=np.float32)
    no_contiguo = arreglo.T if vista == "transpuesta" else arreglo[:, ::2]

    with pytest.raises(ValueError) as error:
        core.bounds(no_contiguo)

    mensaje = str(error.value)
    assert "contiguo" in mensaje
    assert "np.ascontiguousarray" in mensaje


def test_el_nucleo_rechaza_longitud_no_multiplo_de_3(core: Any) -> None:
    with pytest.raises(ValueError, match="múltiplo de 3"):
        core.bounds(np.zeros(4, dtype=np.float32))


def test_el_nucleo_rechaza_caras_fuera_de_rango(core: Any) -> None:
    with pytest.raises(ValueError) as error:
        core.normals(VERTICES, np.array([0, 1, 9], dtype=np.uint32))

    mensaje = str(error.value)
    assert "índice 9" in mensaje
    assert "V = 3" in mensaje


def test_el_nucleo_rechaza_una_malla_sin_vertices(core: Any) -> None:
    with pytest.raises(ValueError, match="búfer vacío"):
        core.bounds(np.zeros((0, 3), dtype=np.float32))


@pytest.mark.parametrize("valor", [np.nan, np.inf, -np.inf])
def test_el_nucleo_rechaza_valores_no_finitos(core: Any, valor: float) -> None:
    vertices = np.array([0.0, 0.0, 0.0, valor, 0.0, 0.0, 0.0, 1.0, 0.0], dtype=np.float32)

    with pytest.raises(ValueError, match="finitos"):
        core.bounds(vertices)


def test_el_nucleo_rechaza_caras_int32_sin_reinterpretar(core: Any) -> None:
    """Riesgo T3: ``int32`` crudo da ``TypeError`` con el remedio exacto."""
    with pytest.raises(TypeError) as error:
        core.normals(VERTICES, CARAS)

    assert "faces.view(np.uint32)" in str(error.value)


# ------------------------------------------------- envoltorio (py_bridge)


def test_el_envoltorio_normaliza_float64_y_no_contiguo(core: Any) -> None:
    """RF-09: el usuario no garantiza dtype ni contigüidad; aquí no es error."""
    referencia = geometry.normals(VERTICES, CARAS)

    como_float64 = geometry.normals(VERTICES.astype(np.float64), CARAS.astype(np.int64))

    grande = np.zeros((6, 6), dtype=np.float32)
    grande[:3, :3] = VERTICES.reshape(3, 3)
    no_contiguo = grande[::2, ::2]
    assert no_contiguo.shape == (3, 3)
    assert not no_contiguo.flags.c_contiguous
    desde_no_contiguo = geometry.normals(no_contiguo, CARAS)

    assert np.array_equal(referencia, como_float64)
    assert desde_no_contiguo.shape == (3, 3)


@pytest.mark.parametrize(
    "vertices",
    [
        pytest.param(np.array(["a", "b", "c"]), id="texto"),
        pytest.param(np.array([object()]), id="objetos"),
    ],
)
def test_el_envoltorio_rechaza_dtype_no_numerico(vertices: np.ndarray) -> None:
    with pytest.raises(TypeError, match="vertices"):
        geometry.as_vertices(vertices)


@pytest.mark.parametrize(
    "vertices",
    [
        pytest.param(np.zeros(3, dtype=np.float32), id="unidimensional"),
        pytest.param(np.zeros((4, 2), dtype=np.float32), id="dos_columnas"),
        pytest.param(np.zeros((2, 3, 1), dtype=np.float32), id="tres_dimensiones"),
    ],
)
def test_el_envoltorio_rechaza_formas_que_no_son_v_por_3(vertices: np.ndarray) -> None:
    with pytest.raises(ValueError) as error:
        geometry.as_vertices(vertices)

    assert "(V, 3)" in str(error.value)


def test_el_envoltorio_rechaza_caras_no_enteras() -> None:
    with pytest.raises(TypeError, match="enteros"):
        geometry.as_faces_u32(np.zeros((2, 3), dtype=np.float32))


def test_el_envoltorio_rechaza_caras_negativas() -> None:
    with pytest.raises(ValueError, match="no negativos"):
        geometry.as_faces_u32(np.array([[-1, 0, 1]], dtype=np.int32))


@pytest.mark.parametrize("indice", [2**31, 2**32, 2**40])
def test_el_envoltorio_rechaza_indices_que_no_caben_en_int32(indice: int) -> None:
    with pytest.raises(ValueError) as error:
        geometry.as_faces_u32(np.array([[indice, 0, 1]], dtype=np.int64))

    mensaje = str(error.value)
    assert "2147483647" in mensaje
    assert str(indice) in mensaje


def test_el_envoltorio_rechaza_bytes_de_longitud_incorrecta() -> None:
    with pytest.raises(ValueError, match="bytes"):
        geometry.from_f32_bytes(b"\x00" * 8, rows=1)


# --------------------------------------------------------- supervivencia


def test_el_proceso_sobrevive_a_todas_las_entradas_no_conformes(core: Any) -> None:
    """E-12: ningún caso mata el intérprete; el núcleo sigue respondiendo."""
    intentos = [
        lambda: core.bounds(np.zeros((4, 3), dtype=np.float64)),
        lambda: core.bounds(np.zeros((4, 6), dtype=np.float32)[:, ::2]),
        lambda: core.bounds(np.zeros(4, dtype=np.float32)),
        lambda: core.bounds(np.zeros((0, 3), dtype=np.float32)),
        lambda: core.bounds(np.array([np.nan] * 9, dtype=np.float32)),
        lambda: core.normals(VERTICES, np.array([0, 1, 9], dtype=np.uint32)),
        lambda: core.normals(VERTICES, CARAS),
        lambda: geometry.as_vertices(np.array([["x"]])),
        lambda: geometry.as_faces_u32(np.array([[-1, 0, 1]], dtype=np.int32)),
    ]

    for intento in intentos:
        with pytest.raises((TypeError, ValueError)):
            intento()

    assert core.add(2, 3) == 5
    assert geometry.bounds(VERTICES) == pytest.approx((0.0, 0.0, 0.0, 1.0, 1.0, 0.0))

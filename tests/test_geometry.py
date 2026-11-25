"""Camino sin copia y contrato de `py_bridge.geometry` (T30).

Lo que se demuestra aquí, en este orden:

1. El núcleo lee **solo el protocolo de búfer**: un ``ndarray`` que falla si
   alguien lo recorre como secuencia sigue funcionando.
2. La normalización de `py_bridge` comparte memoria con numpy cuando la entrada
   ya cumple el contrato (RF-09/RF-20).
3. Las operaciones devuelven arreglos propios, escribibles y sin memoria
   compartida con la entrada.
4. `MeshStats.describe()` produce exactamente el texto de la UI.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from py_bridge import geometry
from py_bridge.scene import mesh_from_numpy

pytestmark = pytest.mark.native


class SinSecuencia(np.ndarray):
    """``ndarray`` que lanza si alguien lo recorre como secuencia.

    Es la prueba más barata de que el núcleo no materializó el arreglo: leerlo
    por ``__getitem__``/``__len__``/``__iter__`` haría fallar la llamada.
    """

    def __getitem__(self, key: Any) -> Any:
        raise AssertionError(f"__getitem__ no debe llamarse (clave {key!r})")

    def __len__(self) -> int:
        raise AssertionError("__len__ no debe llamarse")

    def __iter__(self) -> Any:
        raise AssertionError("__iter__ no debe llamarse")


def _rejilla(lado: int = 8) -> np.ndarray:
    """Vértices ``(lado, lado)`` en ``float32`` C-contiguo."""
    ejes = np.arange(lado, dtype=np.float32)
    x, y = np.meshgrid(ejes, ejes)
    return np.stack([x.ravel(), y.ravel(), np.zeros(lado * lado, np.float32)], axis=1)


def test_el_nucleo_lee_solo_el_bufer(core: Any) -> None:
    """RF-20/CA-20: sin ``__len__`` ni ``__getitem__``, solo protocolo de búfer."""
    base = _rejilla()
    espia = base.view(SinSecuencia)

    assert core.bounds(espia) == core.bounds(base)
    assert geometry.bounds(espia) == geometry.bounds(base)


def test_la_normalizacion_comparte_memoria_si_ya_cumple_el_contrato() -> None:
    """`as_vertices` no copia un ``float32`` C-contiguo: es la misma memoria."""
    vertices = _rejilla()
    malla = mesh_from_numpy(vertices, np.zeros((0, 3), np.int32))

    assert malla.vertices.dtype == np.float32
    assert np.shares_memory(malla.vertices, vertices)
    assert np.shares_memory(geometry.as_vertices(vertices), vertices)


def test_as_faces_u32_reinterpreta_sin_copiar() -> None:
    """Riesgo T3: ``int32 → uint32`` con ``view``, sin duplicar los 24 MB."""
    caras = np.arange(36, dtype=np.int32).reshape(12, 3)

    salida = geometry.as_faces_u32(caras)

    assert salida.dtype == np.uint32
    assert np.shares_memory(salida, caras)


def test_bounds_del_cubo(core: Any, cubo: tuple[np.ndarray, np.ndarray]) -> None:
    vertices, _ = cubo

    assert geometry.bounds(vertices) == pytest.approx((-0.5, -0.5, -0.5, 0.5, 0.5, 0.5))


def test_normals_del_cubo_son_unitarias_y_hacia_fuera(
    core: Any, cubo: tuple[np.ndarray, np.ndarray]
) -> None:
    vertices, caras = cubo
    normales = geometry.normals(vertices, caras)

    assert normales.shape == (8, 3)
    assert normales.dtype == np.float32
    assert np.allclose(np.linalg.norm(normales, axis=1), 1.0, atol=1e-6)
    # Son normales ponderadas por área: en este cubo no coinciden con la diagonal
    # del vértice, pero el coseno con ella debe ser claramente positivo (hacia fuera).
    coseno = np.einsum("ij,ij->i", normales, vertices) / np.linalg.norm(vertices, axis=1)
    assert np.all(coseno > 0.9), coseno


def test_las_salidas_son_propias_y_escribibles(
    core: Any, cubo: tuple[np.ndarray, np.ndarray]
) -> None:
    vertices, caras = cubo

    for salida in (
        geometry.normals(vertices, caras),
        geometry.normalize_unit_aabb(vertices),
    ):
        assert salida.flags.writeable
        assert salida.flags.c_contiguous
        assert not np.shares_memory(salida, vertices)
        salida[0, 0] = 0.0  # no debe lanzar


def test_normalize_no_modifica_la_entrada(
    core: Any, cubo: tuple[np.ndarray, np.ndarray]
) -> None:
    vertices, _ = cubo
    copia = vertices.copy()

    geometry.normalize_unit_aabb(vertices)

    assert np.array_equal(vertices, copia)


def test_normalize_escala_la_caja_a_la_unidad(core: Any) -> None:
    """CA-23: centro en el origen y mayor extensión en ``[-1, 1]``."""
    vertices = np.array(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 6.0]],
        dtype=np.float32,
    )

    salida = geometry.normalize_unit_aabb(vertices)
    caja = geometry.bounds(salida)

    assert caja[0] == pytest.approx(-1.0 / 3.0, abs=1e-6)
    assert caja[3] == pytest.approx(1.0 / 3.0, abs=1e-6)
    assert caja[2] == pytest.approx(-1.0, abs=1e-6)
    assert caja[5] == pytest.approx(1.0, abs=1e-6)


def test_normalize_con_extension_nula_solo_traslada(core: Any) -> None:
    """CA-23: todos los vértices coinciden → resultado en el origen, sin NaN."""
    vertices = np.full((4, 3), 2.5, dtype=np.float32)

    salida = geometry.normalize_unit_aabb(vertices)

    assert salida.shape == vertices.shape
    assert np.all(salida == 0.0)


def test_mesh_stats_describe_formato_exacto(
    core: Any, cubo: tuple[np.ndarray, np.ndarray]
) -> None:
    """D-13: texto exacto de la barra de estado, sin separadores de miles."""
    vertices, caras = cubo

    estadisticas = geometry.mesh_stats(vertices, caras)

    assert estadisticas.vertex_count == 8
    assert estadisticas.face_count == 12
    assert estadisticas.bounds == pytest.approx((-0.5, -0.5, -0.5, 0.5, 0.5, 0.5))
    # 12 aristas de longitud 1 + 6 diagonales de cara de longitud √2.
    assert estadisticas.total_edge_length == pytest.approx(12.0 + 6.0 * np.sqrt(2.0))
    assert estadisticas.describe() == (
        "8 vértices · 12 caras · caja [-0.5, -0.5, -0.5] → [0.5, 0.5, 0.5] · "
        "aristas 20.4853"
    )


def test_mesh_stats_sin_caras(core: Any, cubo: tuple[np.ndarray, np.ndarray]) -> None:
    """RF-18: una malla sin caras es válida (0 caras, 0 aristas)."""
    vertices, _ = cubo

    estadisticas = geometry.mesh_stats(vertices, np.zeros((0, 3), np.int32))

    assert estadisticas.face_count == 0
    assert estadisticas.total_edge_length == 0.0
    assert estadisticas.describe().endswith("aristas 0")


def test_from_f32_bytes_devuelve_arreglo_propio() -> None:
    """La salida del núcleo se decodifica little-endian y se copia a memoria propia."""
    original = np.array([[1.5, -2.0, 3.0], [0.0, 0.25, -1.0]], dtype="<f4")
    decodificado = geometry.from_f32_bytes(original.tobytes(), rows=2)

    assert decodificado.shape == (2, 3)
    assert decodificado.dtype == np.float32
    assert np.array_equal(decodificado, original)
    assert decodificado.flags.writeable
    assert not np.shares_memory(decodificado, original)

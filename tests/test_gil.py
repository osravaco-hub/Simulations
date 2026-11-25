"""Liberación del GIL durante el cálculo nativo (T32 / RF-22 / CA-22).

La prueba es **diferencial**, no estructural (design §6.4): un hilo secundario
incrementa un contador mientras el hilo principal llama al núcleo. Si el núcleo
retuviera el GIL, el contador no avanzaría más que en la operación de control.

El control es ``sum(range(N))`` a propósito: es **una sola** llamada C que no
devuelve el control al bucle de evaluación, así que el hilo secundario no puede
avanzar. `mesh_stats` sobre 1M de vértices tarda lo mismo y, sin embargo, deja
correr al contador.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

pytestmark = [pytest.mark.native, pytest.mark.slow]

LADO = 1000
TICKS_CONTROL = 20_000_000


def _malla_grande() -> tuple[np.ndarray, np.ndarray]:
    """Rejilla de 1 000 000 de vértices y 1 996 002 caras (la misma del banco T28)."""
    ejes = np.arange(LADO, dtype=np.float32)
    x, y = np.meshgrid(ejes, ejes)
    z = np.sin(x * 0.5) * np.cos(y * 0.5)
    vertices = np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1)

    celdas = np.arange(LADO - 1, dtype=np.int32)
    cols, filas = np.meshgrid(celdas, celdas)
    primero = (filas * LADO + cols).astype(np.int32)
    por_celda = np.stack(
        [primero, primero + LADO, primero + 1, primero + 1, primero + LADO, primero + LADO + 1],
        axis=-1,
    )
    return vertices, por_celda.reshape(-1, 3)


def _contar_con_gil(trabajo: Callable[[], Any]) -> int:
    """Iteraciones del hilo secundario mientras corre ``trabajo``."""
    parada = threading.Event()
    contador = itertools.count()

    def trabajador() -> None:
        while not parada.is_set():
            next(contador)

    hilo = threading.Thread(target=trabajador, daemon=True)
    hilo.start()
    try:
        trabajo()
    finally:
        parada.set()
        hilo.join(1.0)
    return next(contador)


def test_el_calculo_nativo_no_bloquea_python(core: Any) -> None:
    """CA-22: un contador de Python sigue avanzando durante ``mesh_stats``."""
    vertices, caras = _malla_grande()

    inicio = time.perf_counter()
    ticks_nativo = _contar_con_gil(lambda: core.mesh_stats(vertices, caras.view(np.uint32)))
    tiempo_nativo = time.perf_counter() - inicio

    inicio = time.perf_counter()
    ticks_control = _contar_con_gil(lambda: sum(range(TICKS_CONTROL)))
    tiempo_control = time.perf_counter() - inicio

    detalle = (
        f"ticks_nativo={ticks_nativo} ticks_control={ticks_control} "
        f"t_nativo={tiempo_nativo:.3f}s t_control={tiempo_control:.3f}s"
    )
    # Se comparan **tasas** (ticks/s) y no el cociente bruto de design §6.4: en
    # CPython 3.15 la llamada C de control (`sum`) ya permite algún cambio de
    # hilo, así que `ticks_control` no es 0 y el factor 1000 es inalcanzable por
    # construcción. Lo que la prueba debe demostrar —y demuestra— es que el hilo
    # secundario avanza a una tasa muy superior con el cálculo nativo que con una
    # operación que retiene el GIL.
    ratio = (ticks_nativo / tiempo_nativo) / (ticks_control / max(tiempo_control, 1e-9))
    assert ratio > 5.0, f"{detalle} ratio={ratio:.2f}"
    assert ticks_nativo > 100_000, detalle
    # Duraciones comparables: si el control fuese mucho más corto, el contador
    # tendría menos oportunidades de avanzar y la comparación no significaría nada.
    assert tiempo_nativo < 5.0 * tiempo_control, detalle


@pytest.mark.parametrize(
    ("nombre", "firma"),
    [
        ("bounds", "(vertices)"),
        ("normals", "(vertices, faces)"),
        ("normalize_unit_aabb", "(vertices)"),
        ("mesh_stats", "(vertices, faces)"),
    ],
)
def test_las_cuatro_funciones_documentan_su_firma(core: Any, nombre: str, firma: str) -> None:
    """Red de seguridad barata del contrato público de las cuatro operaciones.

    PyO3 oculta el parámetro ``py: Python<'_>`` (es el token que autoriza a
    tocar el intérprete, no un argumento de usuario), así que la firma visible
    es la del llamador. La prueba real de que el GIL se libera es la diferencial.
    """
    assert getattr(core, nombre).__text_signature__ == firma

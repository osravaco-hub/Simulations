"""Envoltorio numpy ↔ núcleo nativo para las operaciones geométricas.

Esta es la **única** capa que conoce a la vez numpy y la extensión `core_rust`
(regla de dependencias de `AGENTS.md`): normaliza dtype y contigüidad, delega el
cálculo en el núcleo (que trabaja con búferes planos sin copia y con el GIL
liberado) y devuelve `numpy` o :class:`MeshStats`.

Contrato (design §4.2 y §4.7):

- Los errores del núcleo se propagan **sin envolver** (D-05): el usuario ve el
  `TypeError`/`ValueError` original, con el argumento y el remedio en el mensaje.
- Las salidas propias (`normals`, `normalize_unit_aabb`) son siempre `(V, 3)`
  `float32`, C-contiguas, escribibles y sin memoria compartida con la entrada.
- `bounds` es un alias de tipo, no una clase: el diseño (§7) evita un envoltorio
  que invite a confundirlo con una caja mutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from py_bridge.native import load_core

__all__ = [
    "Bounds",
    "MeshStats",
    "as_faces_u32",
    "as_vertices",
    "bounds",
    "from_f32_bytes",
    "mesh_stats",
    "normalize_unit_aabb",
    "normals",
]

#: Caja alineada a los ejes: ``(min_x, min_y, min_z, max_x, max_y, max_z)``.
Bounds = tuple[float, float, float, float, float, float]

_INT32_MIN: Final[int] = int(np.iinfo(np.int32).min)
_INT32_MAX: Final[int] = int(np.iinfo(np.int32).max)
_DECIMALES: Final[int] = 4


@dataclass(frozen=True, slots=True)
class MeshStats:
    """Estadísticas de una malla (RF-19d).

    Es un tipo de datos puro de `py_bridge`: `app/` puede recibirlo y formatearlo
    sin tocar numpy (`describe()` devuelve el texto listo para la barra de
    estado).
    """

    vertex_count: int
    face_count: int
    bounds: Bounds
    total_edge_length: float

    def describe(self) -> str:
        """Texto para la UI: conteos, caja y longitud de aristas.

        Formato exacto (D-13, **sin** separadores de miles)::

            8 vértices · 12 caras · caja [-0.5, -0.5, -0.5] → [0.5, 0.5, 0.5] · aristas 8.4853
        """
        x0, y0, z0, x1, y1, z1 = self.bounds
        minimo = ", ".join(_numero(valor) for valor in (x0, y0, z0))
        maximo = ", ".join(_numero(valor) for valor in (x1, y1, z1))
        return (
            f"{self.vertex_count} vértices · {self.face_count} caras · "
            f"caja [{minimo}] → [{maximo}] · aristas {_numero(self.total_edge_length)}"
        )


def _numero(valor: float) -> str:
    """Formatea un número sin separadores de miles y sin ceros sobrantes."""
    texto = f"{float(valor):.{_DECIMALES}f}".rstrip("0").rstrip(".")
    return "0" if texto in {"", "-0"} else texto


def as_vertices(vertices: Any) -> np.ndarray:
    """Normaliza a ``(V, 3) float32`` C-contiguo antes de entrar al núcleo (RF-09).

    Acepta cualquier cosa que ``numpy`` pueda interpretar como arreglo numérico.
    Un dtype no numérico es un error de tipo; una forma distinta de ``(V, 3)``,
    un error de valor. Ninguna de las dos copia si el arreglo ya cumple el
    contrato: ``ascontiguousarray`` devuelve el mismo objeto.
    """
    array = np.asarray(vertices)
    if array.dtype.kind not in "iuf":
        raise TypeError(
            f"vertices: se esperaba un arreglo numérico; se recibió dtype {array.dtype}"
        )
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError(f"vertices: se esperaba forma (V, 3); se recibió {array.shape}")
    return np.ascontiguousarray(array, dtype=np.float32)


def as_faces_u32(faces: Any) -> np.ndarray:
    """Normaliza a ``(F, 3) uint32`` C-contiguo, reinterpretando sin copiar (riesgo T3).

    El contrato de `Mesh` guarda los índices como ``int32`` (RF-08) y el núcleo
    los pide como ``uint32``; la reinterpretación es válida porque ``Mesh`` ya
    garantiza índices no negativos. Aquí se rechazan los negativos y los que no
    caben en ``int32`` (D-2) **antes** de convertir, para no truncar en silencio.
    """
    array = np.asarray(faces)
    if array.dtype.kind not in "iu":
        raise TypeError(
            f"faces: se esperaba un arreglo de enteros; se recibió dtype {array.dtype}"
        )
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError(f"faces: se esperaba forma (F, 3); se recibió {array.shape}")
    if array.size:
        minimo = int(array.min())
        maximo = int(array.max())
        if minimo < 0:
            raise ValueError(f"faces: se esperaba índices no negativos; se recibió {minimo}")
        if maximo > _INT32_MAX:
            raise ValueError(
                f"faces: se esperaba un índice de vértice en [0, {_INT32_MAX}] (int32); "
                f"se recibió {maximo}"
            )
    return np.ascontiguousarray(array, dtype=np.int32).view(np.uint32)


def from_f32_bytes(raw: bytes, rows: int) -> np.ndarray:
    """Decodifica el ``bytes`` little-endian del núcleo en ``(rows, 3) float32`` propio.

    ``np.frombuffer`` no copia (y devuelve un arreglo de solo lectura); la copia
    explícita es lo que garantiza un arreglo escribible y de tipo nativo, también
    en plataformas big-endian (donde ``"<f4"`` no es el dtype nativo).
    """
    if rows < 0:
        raise ValueError(f"filas: se esperaba un entero no negativo; se recibió {rows}")
    esperado = rows * 3 * 4
    if len(raw) != esperado:
        raise ValueError(
            f"bytes: se esperaban {esperado} bytes (12 por vértice); se recibieron {len(raw)}"
        )
    planos = np.frombuffer(raw, dtype="<f4", count=rows * 3)
    return np.array(planos.reshape(rows, 3), dtype=np.float32, order="C", copy=True)


def bounds(vertices: Any) -> Bounds:
    """Caja alineada a los ejes de ``vertices`` (RF-19a).

    Devuelve ``(min_x, min_y, min_z, max_x, max_y, max_z)``.
    """
    return tuple(load_core().bounds(as_vertices(vertices)))  # type: ignore[return-value]


def normals(vertices: Any, faces: Any) -> np.ndarray:
    """Una normal por vértice, ``(V, 3) float32`` (RF-19b).

    Vértices sin caras, caras degeneradas o sumas que se cancelan devuelven
    ``(0, 0, 0)``; nunca ``NaN``. Un arreglo de caras vacío es válido.
    """
    vertices_c = as_vertices(vertices)
    raw = load_core().normals(vertices_c, as_faces_u32(faces))
    return from_f32_bytes(raw, vertices_c.shape[0])


def normalize_unit_aabb(vertices: Any) -> np.ndarray:
    """Vértices centrados en el origen y escalados a ``[-1, 1]`` (RF-19c).

    Trabaja sobre una salida nueva: la entrada **no** se modifica. Si la mayor
    extensión es nula (todos los vértices coinciden) solo se traslada.
    """
    vertices_c = as_vertices(vertices)
    raw = load_core().normalize_unit_aabb(vertices_c)
    return from_f32_bytes(raw, vertices_c.shape[0])


def mesh_stats(vertices: Any, faces: Any) -> MeshStats:
    """Conteos, caja y longitud total de aristas únicas (RF-19d)."""
    vertices_c = as_vertices(vertices)
    vertex_count, face_count, box, total = load_core().mesh_stats(
        vertices_c, as_faces_u32(faces)
    )
    x0, y0, z0, x1, y1, z1 = (float(valor) for valor in box)
    return MeshStats(
        vertex_count=int(vertex_count),
        face_count=int(face_count),
        bounds=(x0, y0, z0, x1, y1, z1),
        total_edge_length=float(total),
    )

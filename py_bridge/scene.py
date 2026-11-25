"""Contrato de escena de Rig Studio: modelo inmutable y documento JSON v1.

Este módulo es la única autoridad sobre la forma de una escena: valida las
invariantes de RF-09 al construir, serializa de forma determinista byte a byte
(RF-10) y deriva los huesos de ``parents`` (RF-11). No importa ``core_rust`` ni
``torch``: aquí solo vive el contrato de datos, no el cálculo geométrico.

Reglas que el documento JSON v1 respeta y que este módulo verifica:

* ``schema_version`` es un entero >= 1 siempre presente.
* Las listas numéricas son **planas** y en orden fila por fila (``row-major``);
  ``joints`` incluido.
* ``mesh`` y ``skeleton`` pueden ser ``null``; un documento sin malla es válido
  para el consumidor (el visor lo muestra vacío), pero el productor emite
  siempre el esqueleto derivado de ``parents``.
* ``bones`` nunca se acepta como entrada: se recalcula desde ``parents``.
* Los conteos (``vertex_count``, ``face_count``, ``joint_count``,
  ``bone_count``) son informativos y se **verifican** al parsear.

Semántica de préstamo (RF-09, última frase): ``Mesh`` y ``Skeleton`` normalizan
dtype y contigüidad copiando **solo** cuando hace falta. Si el array recibido ya
tiene el dtype correcto y es C-contiguo, el modelo comparte su memoria (no se
copian 12 MB por malla). Los atributos se exponen como vistas de solo lectura;
la inmutabilidad es un contrato del atributo, no una copia defensiva: si el
llamador conserva y muta el array que prestó, el modelo lo verá.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import numpy as np

SCHEMA_VERSION: Final[int] = 1
"""Versión del contrato de escena que emite este módulo."""

ProgressCallback = Callable[[float], None]
"""Recibe la fracción completada en ``[0.0, 1.0]``. Puede lanzar para abortar."""

_CHUNK_ROWS: Final[int] = 65_536
"""Filas por bloque al convertir arrays a listas planas (progreso y cancelación)."""

_INT32_MIN: Final[int] = int(np.iinfo(np.int32).min)
_INT32_MAX: Final[int] = int(np.iinfo(np.int32).max)
"""Límites de ``int32``: el cast ``numpy`` no los comprueba (D-2, verificación §7)."""

_SCENE_KEYS: Final[tuple[str, ...]] = ("schema_version", "name", "mesh", "skeleton", "metadata")
_MESH_KEYS: Final[tuple[str, ...]] = ("vertices", "faces", "normals", "vertex_count", "face_count")
_SKELETON_KEYS: Final[tuple[str, ...]] = (
    "joints",
    "parents",
    "names",
    "bones",
    "joint_count",
    "bone_count",
)

_AUSENTE = object()
"""Centinela para distinguir una clave ausente de un valor ``None``."""


class SceneError(ValueError):
    """Violación del contrato de escena.

    El mensaje nombra el campo afectado, el valor o forma esperado y el valor o
    forma recibido. Hereda de ``ValueError`` para que un llamador genérico pueda
    capturarlo como error de valor.
    """


# --------------------------------------------------------------------------- #
# Utilidades internas de validación y formato
# --------------------------------------------------------------------------- #


def _recibido(value: Any) -> str:
    """Representación corta y estable de un valor recibido, para mensajes de error."""
    if value is None:
        return "null"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (bool, int, float)):
        return json.dumps(value)
    return type(value).__name__


def _como_array(value: Any, campo: str) -> np.ndarray:
    """Convierte a ``ndarray`` conservando el dtype original para poder diagnosticarlo."""
    if isinstance(value, np.ndarray):
        return value
    try:
        return np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise SceneError(
            f"{campo}: se esperaba un array; se recibió {type(value).__name__} ({exc})"
        ) from exc


def _secuencia(value: Any, campo: str) -> list[Any]:
    """Normaliza una secuencia de entrada a lista, rechazando cadenas sueltas."""
    if isinstance(value, (str, bytes)):
        raise SceneError(f"{campo}: se esperaba una secuencia; se recibió {type(value).__name__}")
    if isinstance(value, np.ndarray):
        return value.tolist()
    try:
        return list(value)
    except TypeError as exc:
        raise SceneError(
            f"{campo}: se esperaba una secuencia; se recibió {type(value).__name__}"
        ) from exc


def _congelar(array: np.ndarray) -> np.ndarray:
    """Copia solo si hace falta (contigüidad) y devuelve una vista de solo lectura."""
    contiguo = np.ascontiguousarray(array)
    vista = contiguo.view()
    vista.flags.writeable = False
    return vista


def _flat(array: np.ndarray) -> list[Any]:
    """Lista plana *row-major* (copia) del array."""
    return array.reshape(-1).tolist()


def _verificar_conteo(
    data: Mapping[str, Any],
    clave: str,
    esperado: int,
    campo: str,
    formula: str,
) -> None:
    """Comprueba un conteo declarado contra el valor derivado, si está presente."""
    if clave not in data:
        return
    recibido = data[clave]
    if isinstance(recibido, bool) or not isinstance(recibido, int) or recibido != esperado:
        raise SceneError(
            f"{campo}: se esperaba {esperado} ({formula}); se recibió {_recibido(recibido)}"
        )


def _rechazar_claves(data: Mapping[str, Any], ambito: str, admitidas: tuple[str, ...]) -> None:
    """Rechaza claves desconocidas listando las admitidas."""
    desconocidas = [clave for clave in data if clave not in admitidas]
    if not desconocidas:
        return
    culpable = sorted(str(clave) for clave in desconocidas)[0]
    raise SceneError(
        f'{ambito}: clave desconocida "{culpable}" (claves admitidas: {", ".join(admitidas)})'
    )


def _plano(value: Any, campo: str, columnas: int) -> np.ndarray:
    """Valida una lista plana y la devuelve como ``ndarray`` 1-D de su dtype original."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SceneError(
            f"{campo}: se esperaba una lista plana; se recibió {type(value).__name__}"
        )
    try:
        plano = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise SceneError(
            f"{campo}: se esperaba una lista plana de números; se recibió {type(value).__name__}"
        ) from exc
    if plano.ndim != 1:
        raise SceneError(
            f"{campo}: se esperaba una lista plana row-major; se recibió forma {plano.shape}"
        )
    if plano.size % columnas:
        raise SceneError(
            f"{campo}: se esperaba una longitud múltiplo de {columnas}; se recibió {plano.size}"
        )
    return plano


def _matriz_float32(value: Any, campo: str, columnas: int = 3) -> np.ndarray:
    """Convierte una lista plana numérica a matriz ``(-1, columnas)`` de ``float32``."""
    plano = _plano(value, campo, columnas)
    if plano.size == 0:
        # Una lista vacía no tiene elementos que diagnosticar y ``np.asarray([])``
        # la infiere como ``float64``; se devuelve ya con el dtype del contrato para
        # no confundir "vacío" con "tipo equivocado" (D-1). No relaja la validación:
        # cualquier elemento no numérico en una lista no vacía sigue rechazándose.
        return np.zeros((0, columnas), dtype=np.float32)
    if plano.dtype.kind not in "iuf":
        raise SceneError(
            f"{campo}: se esperaba una lista de números; se recibió dtype {plano.dtype}"
        )
    try:
        concreto = np.ascontiguousarray(plano, dtype=np.float32)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensa ante dtypes exóticos
        raise SceneError(
            f"{campo}: se esperaba una lista de números; se recibió dtype {plano.dtype}"
        ) from exc
    return concreto.reshape(-1, columnas)


def _matriz_int32(value: Any, campo: str, columnas: int = 3) -> np.ndarray:
    """Convierte una lista plana de enteros a matriz ``(-1, columnas)`` de ``int32``.

    El rango se comprueba **antes** del cast: ``np.ascontiguousarray(..., dtype=np.int32)``
    trunca en silencio los enteros que no caben (``2**40`` se convierte en ``0``), lo
    que aceptaría índices de cara inválidos (D-2, verificación §7). El rango de
    vértices ``[0, V)`` se valida después en :meth:`Mesh.__post_init__`, que es el
    único que conoce ``V`` (diseño §3.2); aquí solo se garantiza que el cast a
    ``int32`` es exacto.
    """
    plano = _plano(value, campo, columnas)
    if plano.size == 0:
        # Igual que en ``_matriz_float32``: vacío es válido para ``faces`` (F = 0).
        return np.zeros((0, columnas), dtype=np.int32)
    if plano.dtype.kind not in "iu":
        raise SceneError(
            f"{campo}: se esperaba una lista de enteros; se recibió dtype {plano.dtype}"
        )
    minimo = int(plano.min())
    maximo = int(plano.max())
    if minimo < _INT32_MIN or maximo > _INT32_MAX:
        indice = int(np.argmin(plano) if minimo < _INT32_MIN else np.argmax(plano))
        culpable = int(plano[indice])
        raise SceneError(
            f"{campo}: se esperaba un índice de vértice en [0, {_INT32_MAX}] (int32); "
            f"se recibió {culpable} en la posición {indice}"
        )
    try:
        concreto = np.ascontiguousarray(plano, dtype=np.int32)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensa ante dtypes exóticos
        raise SceneError(
            f"{campo}: se esperaba una lista de enteros; se recibió dtype {plano.dtype}"
        ) from exc
    return concreto.reshape(-1, columnas)


def _enteros(value: Any, campo: str) -> list[int]:
    """Normaliza una secuencia de enteros, nombrando el índice culpable si no lo es."""
    items = _secuencia(value, campo)
    salida: list[int] = []
    for indice, item in enumerate(items):
        if isinstance(item, bool) or not isinstance(item, (int, np.integer)):
            raise SceneError(
                f"{campo}[{indice}]: se esperaba un entero; se recibió {_recibido(item)}"
            )
        salida.append(int(item))
    return salida


def _cadenas(value: Any, campo: str) -> tuple[str, ...]:
    """Normaliza una secuencia de cadenas, rechazando elementos que no lo sean."""
    items = _secuencia(value, campo)
    salida: list[str] = []
    for indice, item in enumerate(items):
        if not isinstance(item, str):
            raise SceneError(
                f"{campo}[{indice}]: se esperaba una cadena; se recibió {type(item).__name__}"
            )
        salida.append(item)
    return tuple(salida)


def _canonizar_metadata(value: Any) -> Mapping[str, Any]:
    """Canoniza los metadatos: copia profunda, claves ascendentes y solo tipos JSON."""
    if not isinstance(value, Mapping):
        raise SceneError(
            "Scene.metadata: se esperaba un objeto serializable a JSON; "
            f"se recibió {type(value).__name__}"
        )
    claves_invalidas = [clave for clave in value if not isinstance(clave, str)]
    if claves_invalidas:
        raise SceneError(
            "Scene.metadata: se esperaba un objeto con claves de texto; "
            f"se recibió {type(claves_invalidas[0]).__name__}"
        )
    try:
        texto = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SceneError(
            "Scene.metadata: se esperaba un objeto serializable a JSON; "
            f"se recibió {type(value).__name__}"
        ) from exc
    canonico = json.loads(texto)
    return MappingProxyType(canonico)


def _dumps(document: Any) -> str:
    """Serializa con el formato canónico del contrato (compacto, UTF-8, sin NaN)."""
    try:
        return json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=False,
        )
    except (TypeError, ValueError) as exc:
        raise SceneError(f"la escena contiene un valor no serializable a JSON: {exc}") from exc


# --------------------------------------------------------------------------- #
# Modelo
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Mesh:
    """Malla triangular inmutable.

    Atributos:
        vertices: matriz ``(V, 3)`` de ``float32`` C-contigua y de solo lectura.
        faces: matriz ``(F, 3)`` de ``int32`` C-contigua; todos los índices deben
            estar en ``[0, V)``. ``F`` puede ser 0.
        normals: ``(V, 3)`` de ``float32`` o ``None``.
    """

    vertices: np.ndarray
    faces: np.ndarray
    normals: np.ndarray | None = None

    def __post_init__(self) -> None:
        vertices = _como_array(self.vertices, "Mesh.vertices")
        if vertices.ndim != 2 or vertices.shape[1] != 3 or vertices.dtype != np.float32:
            raise SceneError(
                "Mesh.vertices: se esperaba un array de forma (V, 3) y dtype float32; "
                f"se recibió forma {vertices.shape} y dtype {vertices.dtype}"
            )
        if vertices.shape[0] < 1:
            raise SceneError("Mesh.vertices: se esperaba al menos 1 vértice; se recibieron 0")

        faces = _como_array(self.faces, "Mesh.faces")
        if faces.ndim != 2 or faces.shape[1] != 3 or faces.dtype != np.int32:
            raise SceneError(
                "Mesh.faces: se esperaba un array de forma (F, 3) y dtype int32; "
                f"se recibió forma {faces.shape} y dtype {faces.dtype}"
            )

        vertex_count = int(vertices.shape[0])
        if faces.shape[0] > 0:
            minimo = int(faces.min())
            maximo = int(faces.max())
            if minimo < 0 or maximo >= vertex_count:
                cara, esquina = (int(valor) for valor in np.argwhere(
                    (faces < 0) | (faces >= vertex_count)
                )[0])
                indice = int(faces[cara, esquina])
                raise SceneError(
                    f"Mesh.faces: índice {indice} en la cara {cara} está fuera del rango "
                    f"[0, {vertex_count}); se recibieron {vertex_count} vértices"
                )

        object.__setattr__(self, "vertices", _congelar(vertices))
        object.__setattr__(self, "faces", _congelar(faces))

        if self.normals is None:
            object.__setattr__(self, "normals", None)
            return
        normals = _como_array(self.normals, "Mesh.normals")
        if normals.ndim != 2 or normals.shape != (vertex_count, 3):
            raise SceneError(
                f"Mesh.normals: se esperaba forma (V, 3) = ({vertex_count}, 3); "
                f"se recibió {normals.shape}"
            )
        if normals.dtype != np.float32:
            try:
                normals = np.ascontiguousarray(normals, dtype=np.float32)
            except (TypeError, ValueError) as exc:
                raise SceneError(
                    "Mesh.normals: se esperaba un array numérico de forma "
                    f"(V, 3) = ({vertex_count}, 3); se recibió dtype {normals.dtype}"
                ) from exc
        object.__setattr__(self, "normals", _congelar(normals))

    @property
    def vertex_count(self) -> int:
        """Número de vértices ``V``."""
        return int(self.vertices.shape[0])

    @property
    def face_count(self) -> int:
        """Número de caras triangulares ``F``."""
        return int(self.faces.shape[0])

    def to_dict(self) -> dict[str, Any]:
        """Objeto malla del contrato, con orden de claves fijo y listas planas."""
        return {
            "vertices": _flat(self.vertices),
            "faces": _flat(self.faces),
            "normals": None if self.normals is None else _flat(self.normals),
            "vertex_count": self.vertex_count,
            "face_count": self.face_count,
        }

    def to_json(self) -> str:
        """Objeto malla aislado en JSON canónico (diagnóstico, no documento de escena)."""
        return _dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Mesh:
        """Construye un ``Mesh`` desde el objeto malla del documento JSON."""
        if not isinstance(data, Mapping):
            raise SceneError(f"mesh: se esperaba un objeto; se recibió {type(data).__name__}")
        _rechazar_claves(data, "mesh", _MESH_KEYS)
        for obligatoria in ("vertices", "faces"):
            if obligatoria not in data:
                raise SceneError(f'mesh: falta la clave obligatoria "{obligatoria}"')

        vertices = _matriz_float32(data["vertices"], "mesh.vertices")
        faces = _matriz_int32(data["faces"], "mesh.faces")
        vertex_count = int(vertices.shape[0])

        normals: np.ndarray | None = None
        if data.get("normals") is not None:
            normals = _matriz_float32(data["normals"], "mesh.normals")
            if normals.shape[0] != vertex_count:
                raise SceneError(
                    "mesh.normals: se esperaba una lista plana de longitud "
                    f"3*V = {3 * vertex_count}; se recibió {normals.size}"
                )

        _verificar_conteo(
            data, "vertex_count", vertex_count, "mesh.vertex_count", "len(vertices) / 3"
        )
        _verificar_conteo(
            data, "face_count", int(faces.shape[0]), "mesh.face_count", "len(faces) / 3"
        )
        return cls(vertices=vertices, faces=faces, normals=normals)


@dataclass(frozen=True, slots=True)
class Skeleton:
    """Esqueleto inmutable; la jerarquía vive **solo** en ``parents``.

    Atributos:
        joints: matriz ``(J, 3)`` de ``float32`` C-contigua y de solo lectura.
        parents: tupla de longitud ``J``; ``parents[i]`` es ``-1`` (raíz) o un
            índice estrictamente menor que ``i``, lo que descarta ciclos.
        names: tupla de longitud ``J`` con nombres no vacíos.
    """

    joints: np.ndarray
    parents: tuple[int, ...]
    names: tuple[str, ...]

    def __post_init__(self) -> None:
        joints = _como_array(self.joints, "Skeleton.joints")
        filas = int(joints.shape[0]) if joints.ndim >= 1 else 0
        if joints.ndim != 2 or joints.shape[1] != 3 or joints.dtype != np.float32:
            raise SceneError(
                "Skeleton.joints: se esperaba forma (J, 3) = "
                f"({filas}, 3) y dtype float32; se recibió {joints.shape} y dtype {joints.dtype}"
            )
        if filas < 1:
            raise SceneError(
                "Skeleton.joints: se esperaba al menos 1 articulación; se recibieron 0"
            )

        parents = _enteros(self.parents, "Skeleton.parents")
        if len(parents) != filas:
            raise SceneError(
                "Skeleton.parents: se esperaba longitud J = "
                f"{filas} (número de articulaciones); se recibió {len(parents)}"
            )

        names = _cadenas(self.names, "Skeleton.names")
        if len(names) != filas:
            raise SceneError(
                f"Skeleton.names: se esperaba longitud J = {filas}; se recibió {len(names)}"
            )

        for indice, padre in enumerate(parents):
            if padre == -1:
                continue
            if padre < 0 or padre >= indice:
                raise SceneError(
                    f"Skeleton.parents[{indice}]: se esperaba -1 o un índice en "
                    f"[0, {indice}); se recibió {padre}"
                )
        for indice, nombre in enumerate(names):
            if not nombre:
                raise SceneError(
                    f'Skeleton.names[{indice}]: se esperaba una cadena no vacía; se recibió ""'
                )

        object.__setattr__(self, "joints", _congelar(joints))
        object.__setattr__(self, "parents", tuple(parents))
        object.__setattr__(self, "names", tuple(names))

    @property
    def joint_count(self) -> int:
        """Número de articulaciones ``J``."""
        return int(self.joints.shape[0])

    @property
    def bones(self) -> tuple[tuple[int, int], ...]:
        """Pares ``(hijo, padre)`` derivados de ``parents``; nunca se almacenan."""
        return tuple((indice, padre) for indice, padre in enumerate(self.parents) if padre >= 0)

    def to_dict(self) -> dict[str, Any]:
        """Objeto esqueleto del contrato; ``bones`` se recalcula en cada llamada."""
        huesos = self.bones
        return {
            "joints": _flat(self.joints),
            "parents": list(self.parents),
            "names": list(self.names),
            "bones": [[hijo, padre] for hijo, padre in huesos],
            "joint_count": self.joint_count,
            "bone_count": len(huesos),
        }

    def to_json(self) -> str:
        """Objeto esqueleto aislado en JSON canónico (diagnóstico, no documento de escena)."""
        return _dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Skeleton:
        """Construye un ``Skeleton``; la clave ``bones`` se **ignora** (RF-11)."""
        if not isinstance(data, Mapping):
            raise SceneError(f"skeleton: se esperaba un objeto; se recibió {type(data).__name__}")
        _rechazar_claves(data, "skeleton", _SKELETON_KEYS)
        for obligatoria in ("joints", "parents", "names"):
            if obligatoria not in data:
                raise SceneError(f'skeleton: falta la clave obligatoria "{obligatoria}"')

        joints = _matriz_float32(data["joints"], "skeleton.joints")
        parents = _secuencia(data["parents"], "Skeleton.parents")
        names = _secuencia(data["names"], "Skeleton.names")
        skeleton = cls(joints=joints, parents=tuple(parents), names=tuple(names))

        _verificar_conteo(
            data, "joint_count", skeleton.joint_count, "skeleton.joint_count", "len(joints) / 3"
        )
        _verificar_conteo(
            data,
            "bone_count",
            len(skeleton.bones),
            "skeleton.bone_count",
            "pares derivados de parents",
        )
        return skeleton


@dataclass(frozen=True, slots=True)
class Scene:
    """Escena inmutable: malla, esqueleto opcional, nombre y metadatos JSON.

    ``mesh`` puede ser ``None``: el documento emitido lleva ``"mesh": null`` y el
    visor lo interpreta como estado vacío (RF-15). ``metadata`` se canoniza en el
    constructor (copia profunda con claves ascendentes) y se expone como
    ``MappingProxyType``.
    """

    mesh: Mesh | None = None
    skeleton: Skeleton | None = None
    name: str = "escena"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise SceneError(
                f"Scene.name: se esperaba una cadena no vacía; se recibió {_recibido(self.name)}"
            )
        if self.mesh is not None and not isinstance(self.mesh, Mesh):
            raise SceneError(
                "Scene.mesh: se esperaba un objeto de malla o null; "
                f"se recibió {type(self.mesh).__name__}"
            )
        if self.skeleton is not None and not isinstance(self.skeleton, Skeleton):
            raise SceneError(
                "Scene.skeleton: se esperaba un objeto de esqueleto o null; "
                f"se recibió {type(self.skeleton).__name__}"
            )
        object.__setattr__(self, "metadata", _canonizar_metadata(self.metadata))

    # -------------------------------------------------------------- serialización

    def _document(self, progress: ProgressCallback | None) -> dict[str, Any]:
        """Construye el documento v1, convirtiendo arrays por trozos si hay progreso."""
        arrays: list[np.ndarray] = []
        if self.mesh is not None:
            arrays.append(self.mesh.vertices)
            arrays.append(self.mesh.faces)
            if self.mesh.normals is not None:
                arrays.append(self.mesh.normals)
        if self.skeleton is not None:
            arrays.append(self.skeleton.joints)

        total = 0
        for array in arrays:
            total += max(1, -(-int(array.shape[0]) // _CHUNK_ROWS))
        total = max(total, 1)
        hecho = 0

        def convertir(array: np.ndarray) -> list[Any]:
            nonlocal hecho
            if progress is None:
                return _flat(array)
            salida: list[Any] = []
            filas = int(array.shape[0])
            for inicio in range(0, max(filas, 1), _CHUNK_ROWS):
                salida.extend(array[inicio : inicio + _CHUNK_ROWS].reshape(-1).tolist())
                hecho += 1
                progress(min(hecho / total, 1.0))
            return salida

        malla: dict[str, Any] | None = None
        if self.mesh is not None:
            malla = {
                "vertices": convertir(self.mesh.vertices),
                "faces": convertir(self.mesh.faces),
                "normals": None if self.mesh.normals is None else convertir(self.mesh.normals),
                "vertex_count": self.mesh.vertex_count,
                "face_count": self.mesh.face_count,
            }

        esqueleto: dict[str, Any] | None = None
        if self.skeleton is not None:
            huesos = self.skeleton.bones
            esqueleto = {
                "joints": convertir(self.skeleton.joints),
                "parents": list(self.skeleton.parents),
                "names": list(self.skeleton.names),
                "bones": [[hijo, padre] for hijo, padre in huesos],
                "joint_count": self.skeleton.joint_count,
                "bone_count": len(huesos),
            }

        if progress is not None and hecho / total < 1.0:
            progress(1.0)

        return {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "mesh": malla,
            "skeleton": esqueleto,
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        """Documento JSON v1 como diccionario, con el orden de claves del contrato."""
        return self._document(None)

    def to_json(self, *, progress: ProgressCallback | None = None) -> str:
        """Documento JSON v1 canónico; delega en :func:`to_json`."""
        return to_json(self, progress=progress)

    def validate(self) -> None:
        """Revalida el grafo completo; equivale a un ``from_dict(to_dict())``."""
        Scene.from_dict(self.to_dict())

    # ------------------------------------------------------------------- parseo

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Scene:
        """Parsea un documento v1 estricto (productor estricto, consumidor tolerante)."""
        if not isinstance(data, Mapping):
            raise SceneError(
                f"Scene: se esperaba un objeto JSON; se recibió {type(data).__name__}"
            )
        _rechazar_claves(data, "Scene", _SCENE_KEYS)

        version = data.get("schema_version", _AUSENTE)
        if (
            version is _AUSENTE
            or isinstance(version, bool)
            or not isinstance(version, int)
            or version < 1
        ):
            recibido = "ausente" if version is _AUSENTE else _recibido(version)
            raise SceneError(
                f"schema_version: se esperaba un entero ≥ 1; se recibió {recibido}"
            )
        if version != SCHEMA_VERSION:
            raise SceneError(
                "schema_version: se esperaba 1 (versión soportada); "
                f"se recibió {_recibido(version)}"
            )

        malla_cruda = data.get("mesh", _AUSENTE)
        if malla_cruda is _AUSENTE:
            raise SceneError(
                "Scene.mesh: se esperaba un objeto de malla o null; se recibió ausente"
            )
        if malla_cruda is None:
            mesh: Mesh | None = None
        elif isinstance(malla_cruda, Mapping):
            mesh = Mesh.from_dict(malla_cruda)
        else:
            raise SceneError(
                "Scene.mesh: se esperaba un objeto de malla o null; "
                f"se recibió {_recibido(malla_cruda)}"
            )

        esqueleto_crudo = data.get("skeleton", _AUSENTE)
        if esqueleto_crudo is _AUSENTE:
            raise SceneError(
                "Scene.skeleton: se esperaba un objeto de esqueleto o null; "
                "se recibió ausente"
            )
        if esqueleto_crudo is None:
            skeleton: Skeleton | None = None
        elif isinstance(esqueleto_crudo, Mapping):
            skeleton = Skeleton.from_dict(esqueleto_crudo)
        else:
            raise SceneError(
                "Scene.skeleton: se esperaba un objeto de esqueleto o null; "
                f"se recibió {_recibido(esqueleto_crudo)}"
            )

        return cls(
            mesh=mesh,
            skeleton=skeleton,
            name=data.get("name", "escena"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, text: str) -> Scene:
        """Parsea un documento v1 desde texto JSON."""
        if not isinstance(text, str):
            raise SceneError(
                f"Scene.from_json: se esperaba una cadena; se recibió {type(text).__name__}"
            )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SceneError(
                "el documento no contiene JSON válido: "
                f"{exc.msg} (línea {exc.lineno}, columna {exc.colno})"
            ) from exc
        return cls.from_dict(data)


# --------------------------------------------------------------------------- #
# Helpers de construcción numpy -> modelo
# --------------------------------------------------------------------------- #


def mesh_from_numpy(vertices: Any, faces: Any, normals: Any | None = None) -> Mesh:
    """Construye un :class:`Mesh` desde array-likes, normalizando dtype y contigüidad.

    Copia **solo** si el dtype no es el declarado o el array no es C-contiguo; en
    el caso habitual (``float32`` contiguo) el modelo **presta** la memoria del
    llamador. El contrato de inmutabilidad es del atributo: los arrays internos
    se exponen como vistas de solo lectura.
    """
    matriz_vertices = _normalizar_float32(vertices, "Mesh.vertices")
    matriz_caras = _normalizar_int32(faces, "Mesh.faces")
    matriz_normales = None if normals is None else _normalizar_float32(normals, "Mesh.normals")
    return Mesh(vertices=matriz_vertices, faces=matriz_caras, normals=matriz_normales)


def _normalizar_float32(value: Any, campo: str) -> np.ndarray:
    """``ascontiguousarray(dtype=float32)``: copia solo si es necesario."""
    array = _como_array(value, campo)
    try:
        return np.ascontiguousarray(array, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise SceneError(
            f"{campo}: se esperaba un array numérico de dtype float32; "
            f"se recibió dtype {array.dtype}"
        ) from exc


def _normalizar_int32(value: Any, campo: str) -> np.ndarray:
    """``ascontiguousarray(dtype=int32)`` exigiendo un array de enteros."""
    array = _como_array(value, campo)
    if array.dtype.kind not in "iu":
        raise SceneError(
            f"{campo}: se esperaba un array de enteros de dtype int32; "
            f"se recibió dtype {array.dtype}"
        )
    try:
        return np.ascontiguousarray(array, dtype=np.int32)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensa ante dtypes exóticos
        raise SceneError(
            f"{campo}: se esperaba un array de enteros de dtype int32; "
            f"se recibió dtype {array.dtype}"
        ) from exc


def skeleton_from_numpy(
    joints: Any,
    parents: Sequence[int] | Any,
    names: Sequence[str],
) -> Skeleton:
    """Construye un :class:`Skeleton` desde array-likes de articulaciones y jerarquía."""
    matriz = _normalizar_float32(joints, "Skeleton.joints")
    return Skeleton(joints=matriz, parents=tuple(parents), names=tuple(names))


def scene_from_numpy(
    name: str,
    vertices: Any,
    faces: Any,
    *,
    normals: Any | None = None,
    joints: Any | None = None,
    parents: Sequence[int] | None = None,
    joint_names: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Scene:
    """Atajo numpy -> :class:`Scene`.

    Si ``joints`` es ``None`` se construye una escena sin esqueleto. Con ``joints``,
    ``parents`` es obligatorio (la jerarquía tiene una sola fuente y nunca se
    inventa); si falta ``joint_names`` se generan ``joint_0``, ``joint_1``…
    """
    malla = mesh_from_numpy(vertices, faces, normals)
    if joints is None:
        return Scene(mesh=malla, name=name, metadata=metadata or {})

    if parents is None:
        raise SceneError(
            "Skeleton.parents: se esperaban los progenitores al construir un esqueleto; "
            "se recibió None"
        )
    matriz = _normalizar_float32(joints, "Skeleton.joints")
    if joint_names is None:
        nombres = tuple(f"joint_{indice}" for indice in range(int(matriz.shape[0])))
    else:
        nombres = tuple(joint_names)
    esqueleto = Skeleton(joints=matriz, parents=tuple(parents), names=nombres)
    return Scene(mesh=malla, skeleton=esqueleto, name=name, metadata=metadata or {})


def load_scene_file(path: str | Path) -> Scene:
    """Lee un documento v1 desde disco con errores contextuales en español."""
    ruta = Path(path)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SceneError(f"no se encontró el archivo de escena: {ruta}") from exc
    except OSError as exc:
        raise SceneError(f"no se pudo leer el archivo de escena: {ruta} ({exc})") from exc
    try:
        documento = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise SceneError(
            f"{ruta} no contiene JSON válido: {exc.msg} (línea {exc.lineno}, columna {exc.colno})"
        ) from exc
    return Scene.from_dict(documento)


def to_json(scene: Scene, *, progress: ProgressCallback | None = None) -> str:
    """Serialización canónica del documento v1; determinista byte a byte.

    ``progress`` recibe fracciones crecientes en ``[0.0, 1.0]`` mientras se
    convierten los arrays por bloques de ``_CHUNK_ROWS`` filas. La salida es
    idéntica a la de una sola pasada; si ``progress`` lanza, la serialización se
    aborta sin devolver un documento parcial.
    """
    if not isinstance(scene, Scene):
        raise SceneError(f"to_json: se esperaba una Scene; se recibió {type(scene).__name__}")
    return _dumps(scene._document(progress))

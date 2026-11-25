"""Pruebas del contrato de escena: invariantes, jerarquía y documento JSON v1.

Cubre RF-08…RF-11 (CA-11, CA-12): una prueba por invariante de RF-09, jerarquía
derivada de ``parents``, metadatos canónicos y documento canónico determinista.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import pytest

from py_bridge.scene import (
    SCHEMA_VERSION,
    Mesh,
    Scene,
    SceneError,
    Skeleton,
    load_scene_file,
    mesh_from_numpy,
    scene_from_numpy,
)

# --------------------------------------------------------------------------- #
# Auxiliares locales
# --------------------------------------------------------------------------- #


def _documento(fixtures_dir: Path, nombre: str) -> dict[str, Any]:
    """Carga una fixture como diccionario JSON."""
    return json.loads((fixtures_dir / nombre).read_text(encoding="utf-8"))


def _caras_con_indice_fuera_de_rango() -> Mesh:
    """Malla de 8 vértices con el índice 9 en la cara 3 (invariante c)."""
    caras = np.zeros((12, 3), np.int32)
    caras[3] = (9, 0, 1)
    return Mesh(np.zeros((8, 3), np.float32), caras)


CASOS_INVALIDOS: tuple[tuple[str, Callable[[], object], tuple[str, ...]], ...] = (
    (
        "a1",
        lambda: Mesh(np.zeros((4, 2)), np.zeros((0, 3), np.int32)),
        ("Mesh.vertices", "(V, 3)", "float32", "(4, 2)", "float64"),
    ),
    (
        "a2",
        lambda: Mesh(np.zeros((8, 3), np.float32), np.zeros((12, 4), np.int64)),
        ("Mesh.faces", "(F, 3)", "int32", "(12, 4)", "int64"),
    ),
    (
        "a3",
        lambda: Mesh(
            np.zeros((8, 3), np.float32),
            np.zeros((0, 3), np.int32),
            np.zeros((7, 3), np.float32),
        ),
        ("Mesh.normals", "(8, 3)", "(7, 3)"),
    ),
    (
        "a4",
        lambda: Skeleton(
            np.zeros((5, 2)),
            (-1, 0, 1, 2, 2),
            ("a", "b", "c", "d", "e"),
        ),
        ("Skeleton.joints", "(5, 3)", "float32", "(5, 2)", "float64"),
    ),
    (
        "b",
        lambda: Mesh(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32)),
        ("Mesh.vertices", "al menos 1 vértice", "0"),
    ),
    (
        "c",
        _caras_con_indice_fuera_de_rango,
        ("Mesh.faces", "índice 9", "cara 3", "[0, 8)"),
    ),
    (
        "d1",
        lambda: Skeleton(
            np.zeros((5, 3), np.float32),
            (-1, 0, 1, 2),
            ("a", "b", "c", "d", "e"),
        ),
        ("Skeleton.parents", "longitud J = 5", "4"),
    ),
    (
        "d2",
        lambda: Skeleton(
            np.zeros((5, 3), np.float32),
            (-1, 0, 1, 2, 2),
            ("a", "b", "c", "d", "e", "f"),
        ),
        ("Skeleton.names", "longitud J = 5", "6"),
    ),
    (
        "e",
        lambda: Skeleton(
            np.zeros((5, 3), np.float32),
            (-1, 0, 2, 2, 2),
            ("a", "b", "c", "d", "e"),
        ),
        ("Skeleton.parents[2]", "[0, 2)", "se recibió 2"),
    ),
    (
        "f",
        lambda: Skeleton(
            np.zeros((5, 3), np.float32),
            (-1, 0, 1, 2, 2),
            ("root", "", "head", "arm_l", "arm_r"),
        ),
        ("Skeleton.names[1]", "cadena no vacía", '""'),
    ),
)


# --------------------------------------------------------------------------- #
# Mesh
# --------------------------------------------------------------------------- #


def test_malla_valida_normaliza_y_congela(cubo: tuple[np.ndarray, np.ndarray]) -> None:
    vertices, faces = cubo
    malla = Mesh(vertices=vertices, faces=faces)

    assert malla.vertex_count == 8
    assert malla.face_count == 12
    assert malla.vertices.dtype == np.float32
    assert malla.faces.dtype == np.int32
    assert not malla.vertices.flags.writeable
    assert not malla.faces.flags.writeable
    with pytest.raises(ValueError):
        malla.vertices[0, 0] = 1.0


def test_malla_sin_caras_es_valida() -> None:
    malla = Mesh(np.zeros((3, 3), np.float32), np.zeros((0, 3), np.int32))
    assert malla.face_count == 0
    assert malla.to_dict()["faces"] == []


def test_malla_acepta_normales() -> None:
    normales = np.zeros((8, 3), np.float32)
    malla = Mesh(np.zeros((8, 3), np.float32), np.zeros((0, 3), np.int32), normales)
    assert malla.normals is not None
    assert np.shares_memory(malla.normals, normales)
    assert len(malla.to_dict()["normals"]) == 24


def test_malla_comparte_memoria_si_ya_es_contigua(cubo: tuple[np.ndarray, np.ndarray]) -> None:
    vertices, faces = cubo
    malla = mesh_from_numpy(vertices, faces)
    assert np.shares_memory(malla.vertices, vertices)
    assert np.shares_memory(malla.faces, faces)


def test_malla_copia_cuando_el_dtype_no_coincide(cubo: tuple[np.ndarray, np.ndarray]) -> None:
    vertices, faces = cubo
    malla = mesh_from_numpy(vertices.astype(np.float64), faces)
    assert malla.vertices.dtype == np.float32
    assert not np.shares_memory(malla.vertices, vertices)


def test_documento_malla_orden_de_claves(cubo: tuple[np.ndarray, np.ndarray]) -> None:
    vertices, faces = cubo
    malla = Mesh(vertices, faces)
    documento = malla.to_dict()
    assert list(documento) == ["vertices", "faces", "normals", "vertex_count", "face_count"]
    assert documento["vertex_count"] == 8
    assert documento["face_count"] == 12
    assert len(documento["vertices"]) == 24
    assert len(documento["faces"]) == 36


def test_mesh_to_json_es_objeto_independiente(cubo: tuple[np.ndarray, np.ndarray]) -> None:
    vertices, faces = cubo
    objeto = json.loads(Mesh(vertices, faces).to_json())
    assert "schema_version" not in objeto
    assert objeto["vertex_count"] == 8


@pytest.mark.parametrize(
    ("_invariante", "fabrica", "fragmentos"),
    CASOS_INVALIDOS,
    ids=[caso[0] for caso in CASOS_INVALIDOS],
)
def test_invariantes_de_rf09(
    _invariante: str,
    fabrica: Callable[[], object],
    fragmentos: tuple[str, ...],
) -> None:
    with pytest.raises(SceneError) as excinfo:
        fabrica()
    mensaje = str(excinfo.value)
    for fragmento in fragmentos:
        assert fragmento in mensaje, f"falta {fragmento!r} en {mensaje!r}"
    assert isinstance(excinfo.value, ValueError)


def test_mensaje_de_error_no_es_asercion_de_entrada(cubo: tuple[np.ndarray, np.ndarray]) -> None:
    """La validación usa excepciones, nunca ``assert`` (que se desactiva con ``-O``)."""
    vertices, faces = cubo
    with pytest.raises(SceneError):
        Mesh(vertices[:, :2], faces)


# --------------------------------------------------------------------------- #
# Skeleton
# --------------------------------------------------------------------------- #


def test_bones_derivados() -> None:
    esqueleto = Skeleton(
        joints=np.zeros((4, 3), np.float32),
        parents=(-1, 0, 0, 2),
        names=("root", "a", "b", "c"),
    )
    assert esqueleto.joint_count == 4
    assert esqueleto.bones == ((1, 0), (2, 0), (3, 2))
    assert esqueleto.to_dict()["bones"] == [[1, 0], [2, 0], [3, 2]]
    assert esqueleto.to_dict()["bone_count"] == 3


def test_bones_se_recalculan_al_cambiar_parents() -> None:
    primero = Skeleton(np.zeros((3, 3), np.float32), (-1, 0, 1), ("a", "b", "c"))
    segundo = Skeleton(np.zeros((3, 3), np.float32), (-1, 0, 0), ("a", "b", "c"))
    assert primero.bones == ((1, 0), (2, 1))
    assert segundo.bones == ((1, 0), (2, 0))


def test_bones_no_es_parametro_del_constructor() -> None:
    with pytest.raises(TypeError):
        Skeleton(  # type: ignore[call-arg]
            np.zeros((2, 3), np.float32),
            (-1, 0),
            ("a", "b"),
            bones=((1, 0),),
        )


def test_bones_ignorados_en_entrada(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_mesh_skeleton.json")
    documento["skeleton"]["bones"] = [[4, 4], [0, 3]]

    escena = Scene.from_dict(documento)

    assert escena.skeleton is not None
    assert escena.skeleton.bones == ((1, 0), (2, 1), (3, 2), (4, 2))
    emitido = escena.to_dict()["skeleton"]
    assert emitido is not None
    assert emitido["bones"] == [[1, 0], [2, 1], [3, 2], [4, 2]]


def test_articulaciones_comparte_memoria_y_congela() -> None:
    joints = np.zeros((5, 3), np.float32)
    esqueleto = Skeleton(joints, (-1, 0, 1, 2, 2), ("a", "b", "c", "d", "e"))
    assert np.shares_memory(esqueleto.joints, joints)
    assert not esqueleto.joints.flags.writeable


# --------------------------------------------------------------------------- #
# Scene: composición, metadatos y validación
# --------------------------------------------------------------------------- #


def test_escena_sin_esqueleto(fixtures_dir: Path) -> None:
    escena = load_scene_file(fixtures_dir / "scene_mesh_only.json")
    assert escena.skeleton is None
    assert escena.mesh is not None
    assert escena.mesh.vertex_count == 8

    documento = escena.to_dict()
    assert documento["skeleton"] is None
    assert Scene.from_dict(documento).to_dict() == documento


def test_escena_sin_malla_es_valida() -> None:
    escena = Scene(mesh=None, name="vacia")
    documento = escena.to_dict()
    assert documento["mesh"] is None
    assert Scene.from_dict(documento).mesh is None
    assert Scene.from_json(escena.to_json()).mesh is None


def test_escena_sin_malla_desde_json() -> None:
    texto = '{"schema_version":1,"name":"x","mesh":null,"skeleton":null,"metadata":{}}'
    escena = Scene.from_json(texto)
    assert escena.mesh is None
    assert escena.skeleton is None
    assert escena.to_json() == texto


def test_escena_rechaza_mesh_ausente() -> None:
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict({"schema_version": 1, "skeleton": None, "metadata": {}})
    assert "Scene.mesh" in str(excinfo.value)


def test_escena_rechaza_mesh_de_tipo_incorrecto() -> None:
    with pytest.raises(SceneError) as excinfo:
        Scene(mesh="malla")  # type: ignore[arg-type]
    assert "Scene.mesh" in str(excinfo.value)
    assert "str" in str(excinfo.value)


def test_escena_rechaza_nombre_vacio() -> None:
    with pytest.raises(SceneError) as excinfo:
        Scene(mesh=None, name="")
    assert "Scene.name" in str(excinfo.value)


def test_metadata_es_mappingproxy() -> None:
    escena = Scene(mesh=None, metadata={"b": 1, "a": 2})
    assert isinstance(escena.metadata, MappingProxyType)
    assert list(escena.metadata) == ["a", "b"]
    with pytest.raises(TypeError):
        escena.metadata["a"] = 3  # type: ignore[index]


def test_metadata_no_serializable() -> None:
    with pytest.raises(SceneError) as excinfo:
        Scene(mesh=None, metadata={"x": object()})
    mensaje = str(excinfo.value)
    assert "Scene.metadata" in mensaje
    assert "serializable a JSON" in mensaje


def test_metadata_debe_ser_objeto() -> None:
    with pytest.raises(SceneError) as excinfo:
        Scene(mesh=None, metadata=[("a", 1)])  # type: ignore[arg-type]
    assert "Scene.metadata" in str(excinfo.value)


def test_metadata_claves_ascendentes_y_copia_profunda() -> None:
    original: dict[str, Any] = {"z": 1, "a": {"b": 2, "a": 1}, "lista": [1, 2]}
    escena = Scene(mesh=None, metadata=original)

    original["lista"].append(3)
    assert escena.metadata["lista"] == [1, 2]
    assert list(escena.metadata) == ["a", "lista", "z"]
    anidado = escena.metadata["a"]
    assert list(anidado) == ["a", "b"]
    assert list(escena.to_dict()["metadata"]) == ["a", "lista", "z"]


def test_metadata_no_ascii_se_emite_en_utf8() -> None:
    escena = Scene(mesh=None, metadata={"autor": "ñ"})
    assert '"autor":"ñ"' in escena.to_json()


def test_validate_acepta_escena_valida(escena: Scene) -> None:
    assert escena.validate() is None
    assert Scene(mesh=None).validate() is None


def test_from_json_rechaza_texto_no_json() -> None:
    with pytest.raises(SceneError) as excinfo:
        Scene.from_json("{no es json}")
    assert "JSON válido" in str(excinfo.value)


def test_from_json_rechaza_raiz_no_objeto() -> None:
    with pytest.raises(SceneError) as excinfo:
        Scene.from_json("[]")
    assert "se esperaba un objeto JSON" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Documento: claves, versión y conteos
# --------------------------------------------------------------------------- #


def test_clave_desconocida_en_scene(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_mesh_only.json")
    documento["meshes"] = []
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    mensaje = str(excinfo.value)
    assert 'Scene: clave desconocida "meshes"' in mensaje
    assert "schema_version, name, mesh, skeleton, metadata" in mensaje


def test_clave_desconocida_en_mesh(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_mesh_only.json")
    documento["mesh"]["colors"] = []
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    mensaje = str(excinfo.value)
    assert 'mesh: clave desconocida "colors"' in mensaje
    assert "vertices, faces, normals, vertex_count, face_count" in mensaje


def test_clave_desconocida_en_skeleton(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_mesh_skeleton.json")
    documento["skeleton"]["weights"] = []
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    assert 'skeleton: clave desconocida "weights"' in str(excinfo.value)


def test_schema_version_ausente() -> None:
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict({})
    mensaje = str(excinfo.value)
    assert "schema_version" in mensaje
    assert "ausente" in mensaje


def test_schema_version_no_entera(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_mesh_only.json")
    documento["schema_version"] = "1"
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    mensaje = str(excinfo.value)
    assert "schema_version" in mensaje
    assert '"1"' in mensaje


def test_schema_version_futura(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_v2.json")
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    mensaje = str(excinfo.value)
    assert "versión soportada" in mensaje
    assert "2" in mensaje


def test_fixture_vacia_es_rechazada(fixtures_dir: Path) -> None:
    with pytest.raises(SceneError):
        Scene.from_dict(_documento(fixtures_dir, "scene_empty.json"))


def test_fixture_con_indice_invalido_es_rechazada(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_invalid_face_index.json")
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    assert "fuera del rango" in str(excinfo.value)


def test_conteo_de_vertices_inconsistente(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_mesh_only.json")
    documento["mesh"]["vertex_count"] = 9
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    mensaje = str(excinfo.value)
    assert "mesh.vertex_count" in mensaje
    assert "se esperaba 8" in mensaje
    assert "9" in mensaje


def test_conteo_de_caras_inconsistente(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_mesh_only.json")
    documento["mesh"]["face_count"] = 11
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    assert "mesh.face_count" in str(excinfo.value)


def test_conteo_de_articulaciones_inconsistente(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_mesh_skeleton.json")
    documento["skeleton"]["joint_count"] = 6
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    assert "skeleton.joint_count" in str(excinfo.value)


def test_conteo_de_huesos_inconsistente(fixtures_dir: Path) -> None:
    documento = _documento(fixtures_dir, "scene_mesh_skeleton.json")
    documento["skeleton"]["bone_count"] = 3
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    assert "skeleton.bone_count" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Documento canónico
# --------------------------------------------------------------------------- #


def test_documento_canonico(escena: Scene) -> None:
    texto = escena.to_json()

    assert texto[:2] == '{"'
    assert not texto.endswith("\n")
    documento = json.loads(texto)
    assert list(documento) == ["schema_version", "name", "mesh", "skeleton", "metadata"]
    assert documento["schema_version"] == SCHEMA_VERSION
    assert list(documento["mesh"]) == [
        "vertices",
        "faces",
        "normals",
        "vertex_count",
        "face_count",
    ]
    assert list(documento["skeleton"]) == [
        "joints",
        "parents",
        "names",
        "bones",
        "joint_count",
        "bone_count",
    ]
    assert texto.endswith('"metadata":{"source":"example://cube","units":"m"}}')


def test_to_json_equivale_a_to_dict(escena: Scene) -> None:
    assert json.loads(escena.to_json()) == escena.to_dict()


def test_listas_planas_row_major(escena: Scene) -> None:
    documento = escena.to_dict()
    assert isinstance(documento["mesh"]["vertices"], list)
    assert len(documento["mesh"]["vertices"]) == 24
    assert documento["mesh"]["vertices"][:6] == [-0.5, -0.5, -0.5, 0.5, -0.5, -0.5]
    assert documento["skeleton"]["joints"][:3] == [0.0, -0.5, 0.0]
    assert documento["mesh"]["normals"] is None
    assert isinstance(documento["skeleton"]["parents"], list)


def test_scene_from_numpy_sin_joints(cubo: tuple[np.ndarray, np.ndarray]) -> None:
    vertices, faces = cubo
    escena = scene_from_numpy("cubo", vertices, faces)
    assert escena.skeleton is None
    assert escena.name == "cubo"


def test_scene_from_numpy_sin_parents_es_error(cubo: tuple[np.ndarray, np.ndarray]) -> None:
    vertices, faces = cubo
    with pytest.raises(SceneError) as excinfo:
        scene_from_numpy(
            "cubo",
            vertices,
            faces,
            joints=np.zeros((2, 3), np.float32),
        )
    assert "Skeleton.parents" in str(excinfo.value)


def test_load_scene_file_inexistente(tmp_path: Path) -> None:
    with pytest.raises(SceneError) as excinfo:
        load_scene_file(tmp_path / "no-existe.scene.json")
    assert "no se encontró el archivo de escena" in str(excinfo.value)


def test_load_scene_file_json_invalido(tmp_path: Path) -> None:
    ruta = tmp_path / "roto.scene.json"
    ruta.write_text("{no es json}", encoding="utf-8")
    with pytest.raises(SceneError) as excinfo:
        load_scene_file(ruta)
    assert "no contiene JSON válido" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Regresiones de la verificación (D-1, D-2)
# --------------------------------------------------------------------------- #


def _malla_sin_caras() -> Mesh:
    """Malla válida con ``V = 3`` y ``F = 0`` (estado que el diseño declara válido)."""
    return Mesh(np.zeros((3, 3), np.float32), np.zeros((0, 3), np.int32))


def _documento_con_caras(caras: list[int | float]) -> dict[str, Any]:
    """Documento v1 mínimo de 3 vértices con las caras indicadas."""
    return {
        "schema_version": SCHEMA_VERSION,
        "name": "indices",
        "mesh": {
            "vertices": [0.0] * 9,
            "faces": caras,
            "normals": None,
            "vertex_count": 3,
            "face_count": len(caras) // 3,
        },
        "skeleton": None,
        "metadata": {},
    }


def test_d1_malla_sin_caras_validate_es_none() -> None:
    """D-1: ``validate()`` de una malla con ``F = 0`` no debe lanzar."""
    escena = Scene(mesh=_malla_sin_caras(), name="sin_caras")
    assert escena.validate() is None


def test_d1_malla_sin_caras_round_trip_json() -> None:
    """D-1: ``to_json`` → ``from_dict`` conserva la malla sin caras."""
    escena = Scene(mesh=_malla_sin_caras(), name="sin_caras")
    documento = escena.to_dict()
    assert documento["mesh"]["faces"] == []
    assert documento["mesh"]["face_count"] == 0

    releida = Scene.from_dict(json.loads(escena.to_json()))

    assert releida.to_dict() == documento
    assert releida.mesh is not None
    assert releida.mesh.faces.shape == (0, 3)
    assert releida.mesh.faces.dtype == np.int32


def test_d1_malla_sin_caras_round_trip_archivo(tmp_path: Path) -> None:
    """D-1: el estado válido también sobrevive a ``load_scene_file``."""
    escena = Scene(mesh=_malla_sin_caras(), name="sin_caras")
    ruta = tmp_path / "sin_caras.scene.json"
    ruta.write_text(escena.to_json(), encoding="utf-8")

    releida = load_scene_file(ruta)

    assert releida.to_dict() == escena.to_dict()
    assert releida.mesh is not None
    assert releida.mesh.face_count == 0


def test_d1_normales_vacias_se_rechazan_por_forma() -> None:
    """D-1: ``normals: []`` no es un agujero; lo rechaza la forma ``(V, 3)``."""
    documento = _documento_con_caras([0, 1, 2])
    documento["mesh"]["normals"] = []
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(documento)
    mensaje = str(excinfo.value)
    assert "mesh.normals" in mensaje
    assert "3*V = 9" in mensaje


def test_d1_esqueleto_con_joints_vacio_se_rechaza_por_invariante() -> None:
    """D-1: `joints: []` tampoco es un agujero; lo rechaza «al menos 1 articulación»."""
    with pytest.raises(SceneError) as excinfo:
        Skeleton.from_dict({"joints": [], "parents": [], "names": []})
    assert "al menos 1 articulación" in str(excinfo.value)


def test_lista_de_caras_no_entera_sigue_rechazandose() -> None:
    """D-1 no relaja el tipo: una lista no vacía con flotantes sigue fallando."""
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(_documento_con_caras([1.5, 0, 1]))
    mensaje = str(excinfo.value)
    assert "mesh.faces" in mensaje
    assert "enteros" in mensaje
    assert "float64" in mensaje
    assert isinstance(excinfo.value, ValueError)


_INDICES_FUERA_DE_INT32: tuple[int, ...] = (2**31, 2**32, 2**40, -(2**31) - 1, -(2**40))


@pytest.mark.parametrize(
    "indice",
    _INDICES_FUERA_DE_INT32,
    ids=[str(indice) for indice in _INDICES_FUERA_DE_INT32],
)
def test_d2_indice_fuera_de_int32_es_rechazado(indice: int) -> None:
    """D-2: el rango se valida antes del cast; el índice no se trunca a uno válido."""
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(_documento_con_caras([indice, 0, 1]))
    mensaje = str(excinfo.value)
    assert "mesh.faces" in mensaje
    assert str(indice) in mensaje
    assert "int32" in mensaje
    assert "posición 0" in mensaje


@pytest.mark.parametrize("indice", (0, 1, 2, 2**16 - 1), ids=lambda indice: f"i{indice}")
def test_d2_indices_dentro_de_rango_se_aceptan(indice: int) -> None:
    """D-2: el guard no rechaza índices legítimos (incluidos los mayores que ``uint16``)."""
    documento = _documento_con_caras([indice, 0, 1])
    if indice > 2:
        documento["mesh"]["vertices"] = [0.0] * (3 * (indice + 1))
        documento["mesh"]["vertex_count"] = indice + 1

    escena = Scene.from_dict(documento)

    assert escena.mesh is not None
    assert escena.mesh.faces.tolist() == [[indice, 0, 1]]


def test_d2_int32_maximo_llega_intacto_al_rango_de_vertices() -> None:
    """D-2: ``2**31 - 1`` cabe en ``int32``; lo rechaza ``[0, V)``, no el guard.

    No se puede construir ``V = 2**31`` (25 GB), así que la prueba de que el límite
    superior del guard es exacto consiste en comprobar que el valor llega sin
    truncar al chequeo de vértices: el mensaje nombraría ``2147483647``.
    """
    with pytest.raises(SceneError) as excinfo:
        Scene.from_dict(_documento_con_caras([2**31 - 1, 0, 1]))
    mensaje = str(excinfo.value)
    assert "2147483647" in mensaje
    assert "fuera del rango" in mensaje
    assert "cara 0" in mensaje

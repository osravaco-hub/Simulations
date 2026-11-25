"""Capa de puente entre la UI (PySide6) y el núcleo nativo (Rust).

Responsabilidades:
- Cargar la extensión `core_rust` compilada con maturin/cargo.
- Ofrecer una API Python estable (numpy in / numpy out) que oculte detalles FFI.
- Envolver el backend de aprendizaje profundo (MagicArticulate) con import perezoso
  de `torch`, para que la UI arranque aunque torch no esté instalado.
- Exponer el contrato de escena (modelo inmutable + documento JSON v1).
"""

from py_bridge.geometry import MeshStats
from py_bridge.magicarticulate import (
    ArticulationResult,
    MagicArticulateBackend,
    PendingFeatureError,
)
from py_bridge.native import (
    CoreNotBuiltError,
    CoreStatus,
    core,
    core_status,
    core_version,
    expected_core_version,
    load_core,
)
from py_bridge.scene import (
    SCHEMA_VERSION,
    Mesh,
    Scene,
    SceneError,
    Skeleton,
    load_scene_file,
    mesh_from_numpy,
    scene_from_numpy,
    skeleton_from_numpy,
)

__all__ = [
    # existentes (se conservan para no romper `app/`)
    "ArticulationResult",
    "CoreNotBuiltError",
    "MagicArticulateBackend",
    "core",
    "core_version",
    "load_core",
    # diagnóstico del núcleo (RF-04, RF-07)
    "CoreStatus",
    "core_status",
    "expected_core_version",
    # contrato de escena
    "SCHEMA_VERSION",
    "Mesh",
    "Scene",
    "SceneError",
    "Skeleton",
    "load_scene_file",
    "mesh_from_numpy",
    "scene_from_numpy",
    "skeleton_from_numpy",
    # frontera del backend ML
    "PendingFeatureError",
    # geometría (RF-19d); `py_bridge.geometry` aporta el resto como submódulo
    "MeshStats",
]

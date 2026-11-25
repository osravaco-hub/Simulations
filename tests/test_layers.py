"""Reglas de dependencias entre capas y superficie pública de ``py_bridge``.

Verifica con AST de imports (no con ``sys.modules``) que ``app/`` no conoce
``numpy``, ``torch`` ni ``core_rust``, que ``torch`` solo se importa dentro de
funciones y que el visor no depende de nada externo (RF-27, RF-29, CA-32/CA-33
parciales).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

import py_bridge

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"
PY_BRIDGE = RAIZ / "py_bridge"
VIEWER = RAIZ / "viewer"
CORE = RAIZ / "core_rust"
TESTS = RAIZ / "tests"

#: Exportaciones esperadas en esta fase: las 6 existentes + el contrato de escena
#: y la frontera ML. ``MeshStats`` (T29) y ``CoreStatus``/``core_status``/
#: ``expected_core_version`` (T08) se añadirán cuando existan sus módulos.
EXPORTACIONES_ESPERADAS = {
    "ArticulationResult",
    "CoreNotBuiltError",
    "CoreStatus",
    "MagicArticulateBackend",
    "Mesh",
    "MeshStats",
    "PendingFeatureError",
    "SCHEMA_VERSION",
    "Scene",
    "SceneError",
    "Skeleton",
    "core",
    "core_status",
    "core_version",
    "expected_core_version",
    "load_core",
    "load_scene_file",
    "mesh_from_numpy",
    "scene_from_numpy",
    "skeleton_from_numpy",
}


def _archivos_python(directorio: Path) -> Iterator[Path]:
    """Recorre los ``.py`` de un directorio excluyendo cachés y entornos."""
    for ruta in directorio.rglob("*.py"):
        if "__pycache__" in ruta.parts or ".venv" in ruta.parts:
            continue
        yield ruta


def _imports(ruta: Path) -> set[str]:
    """Conjunto de módulos de primer nivel importados en un archivo."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    modulos: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.update(alias.name.split(".")[0] for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            modulos.add(nodo.module.split(".")[0])
    return modulos


def test_app_no_importa_numpy_torch_ni_core_rust() -> None:
    prohibidos = {"numpy", "torch", "core_rust"}
    for ruta in _archivos_python(APP):
        encontrados = _imports(ruta) & prohibidos
        assert not encontrados, f"{ruta} importa {sorted(encontrados)}"


def test_solo_py_bridge_importa_la_extension_nativa() -> None:
    importadores = [
        ruta
        for directorio in (APP, PY_BRIDGE, TESTS)
        for ruta in _archivos_python(directorio)
        if "core_rust" in _imports(ruta)
    ]
    for ruta in importadores:
        assert PY_BRIDGE in ruta.parents, f"{ruta} importa core_rust fuera de py_bridge"

    native = (PY_BRIDGE / "native.py").read_text(encoding="utf-8")
    assert '_MODULE = "core_rust"' in native
    assert "import_module(_MODULE)" in native


def test_torch_solo_se_importa_dentro_de_funciones() -> None:
    ruta = PY_BRIDGE / "magicarticulate.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Import):
            assert all(alias.name != "torch" for alias in nodo.names), "torch en import de módulo"
        elif isinstance(nodo, ast.ImportFrom):
            assert nodo.module != "torch", "torch en from-import de módulo"


def test_visor_no_depende_de_nada_externo() -> None:
    for ruta in sorted(VIEWER.glob("*.js")):
        texto = ruta.read_text(encoding="utf-8")
        assert "require(" not in texto, f"{ruta} usa CommonJS"
        for linea in texto.splitlines():
            despejada = linea.strip()
            assert not despejada.startswith("import "), f"{ruta} usa módulos ES"
            assert "} from \"" not in despejada, f"{ruta} usa módulos ES"

    html = (VIEWER / "index.html").read_text(encoding="utf-8")
    assert 'src="http' not in html
    assert 'href="http' not in html


def test_pyfunction_solo_en_lib_rs() -> None:
    for ruta in CORE.rglob("*.rs"):
        if "target" in ruta.parts or ruta.name == "lib.rs":
            continue
        assert "#[pyfunction]" not in ruta.read_text(encoding="utf-8"), f"{ruta} declara FFI"


def test_all_exporta_el_contrato_vigente() -> None:
    assert len(py_bridge.__all__) == len(set(py_bridge.__all__))
    assert set(py_bridge.__all__) == EXPORTACIONES_ESPERADAS
    for nombre in py_bridge.__all__:
        assert getattr(py_bridge, nombre) is not None


def test_se_conservan_las_exportaciones_anteriores() -> None:
    anteriores = {
        "ArticulationResult",
        "CoreNotBuiltError",
        "MagicArticulateBackend",
        "core",
        "core_version",
        "load_core",
    }
    assert anteriores <= set(py_bridge.__all__)


def test_version_del_contrato_es_uno() -> None:
    assert py_bridge.SCHEMA_VERSION == 1


def test_pending_feature_error_hereda_de_notimplementederror() -> None:
    assert issubclass(py_bridge.PendingFeatureError, NotImplementedError)


def test_mensaje_de_feature_pendiente_nombra_la_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = py_bridge.MagicArticulateBackend()
    monkeypatch.setattr(backend, "torch_available", lambda: True)

    with pytest.raises(py_bridge.PendingFeatureError) as excinfo:
        backend.load()

    mensaje = str(excinfo.value)
    assert "magicarticulate-backend" in mensaje
    assert not isinstance(excinfo.value, ModuleNotFoundError)


def test_app_no_usa_print_para_errores_de_usuario() -> None:
    """Regla del proyecto: los errores de usuario van a la UI, no a ``print``.

    Hoy ``app/main.py`` conserva ``print`` en los slots de demostración; la
    integración de la barra de estado (T41) los sustituye. Mientras tanto el
    control se limita a los módulos de la capa núcleo del puente.
    """
    ruta = PY_BRIDGE / "scene.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
            assert nodo.func.id != "print", f"{ruta}:{nodo.lineno} usa print()"


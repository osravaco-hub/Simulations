"""Validación por esquema JSON del contrato de escena (RF-12, CA-09, D-14).

Valida las fixtures contra `specs/rig-studio-foundation/scene.schema.json` con
``jsonschema`` draft 2020-12 y comprueba la dirección inversa: el documento que
produce :meth:`Scene.to_dict` cumple el mismo esquema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from py_bridge.scene import Scene, SceneError, scene_from_numpy

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema no está instalado")

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = RAIZ / "specs" / "rig-studio-foundation" / "scene.schema.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _cargar(nombre: str) -> dict[str, Any]:
    """Carga una fixture del contrato como diccionario JSON."""
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validador() -> Any:
    """Validador draft 2020-12 del esquema del contrato."""
    documento = json.loads(ESQUEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(documento)
    return jsonschema.Draft202012Validator(documento)


def test_el_esquema_es_de_draft_2020_12(validador: Any) -> None:
    documento = json.loads(ESQUEMA.read_text(encoding="utf-8"))
    assert documento["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert documento["additionalProperties"] is False
    assert validador is not None


@pytest.mark.parametrize(
    "nombre",
    ["scene_mesh_only.json", "scene_mesh_skeleton.json"],
)
def test_fixture_valida_pasa_el_esquema(validador: Any, nombre: str) -> None:
    validador.validate(_cargar(nombre))


def test_fixture_invalida_falla_en_esquema_y_en_python(validador: Any) -> None:
    documento = _cargar("scene_invalid_face_index.json")
    assert validador.is_valid(documento) is False
    with pytest.raises(SceneError):
        Scene.from_dict(documento)


def test_fixture_con_version_futura_pasa_el_esquema_pero_no_python(validador: Any) -> None:
    documento = _cargar("scene_v2.json")
    assert validador.is_valid(documento) is True
    with pytest.raises(SceneError):
        Scene.from_dict(documento)


def test_el_productor_cumple_el_contrato(validador: Any, escena: Scene) -> None:
    validador.validate(escena.to_dict())
    validador.validate(json.loads(escena.to_json()))


def test_el_productor_sin_esqueleto_cumple_el_contrato(
    validador: Any, cubo: tuple[np.ndarray, np.ndarray]
) -> None:
    vertices, faces = cubo
    escena = scene_from_numpy("cubo", vertices, faces)
    validador.validate(escena.to_dict())


def test_el_esquema_rechaza_claves_desconocidas(validador: Any) -> None:
    documento = _cargar("scene_mesh_only.json")
    documento["extra"] = 1
    assert validador.is_valid(documento) is False


def test_el_esquema_rechaza_indices_negativos(validador: Any) -> None:
    documento = _cargar("scene_mesh_only.json")
    documento["mesh"]["faces"][0] = -1
    assert validador.is_valid(documento) is False

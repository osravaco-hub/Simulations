"""Arnés de pruebas de la UI: pytest-qt y el marcador `gui` (T07).

Se salta el módulo entero si pytest-qt no está instalado, de modo que la suite
rápida (`pytest -q -m "not gui"`) siga funcionando en entornos sin Qt.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytestqt", reason="pytest-qt no está instalado")
pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no está instalado")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402

pytestmark = pytest.mark.gui


def test_qtbot_crea_y_muestra_un_widget(qtbot: pytest.QtBot) -> None:
    """El fixture `qtbot` y el `QApplication` de `conftest.py` conviven."""
    etiqueta = QLabel("Rig Studio")
    etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
    qtbot.addWidget(etiqueta)

    etiqueta.show()
    qtbot.waitExposed(etiqueta)

    assert etiqueta.isVisible()
    assert etiqueta.text() == "Rig Studio"

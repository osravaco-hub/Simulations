"""Rig Studio — ventana principal de tres paneles y punto de entrada.

Distribución:

    ┌────────────┬──────────────────────────┬──────────────────┐
    │ Jerarquía  │ Visor 3D (QWebEngineView)│ Rig / Simulación │
    │ (QTree)    │ viewer/index.html        │ (QTabWidget)     │
    └────────────┴──────────────────────────┴──────────────────┘

Uso:
    python -m app.main
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from py_bridge import core_status

VIEWER_DIR = Path(__file__).resolve().parents[1] / "viewer"
VIEWER_HTML = VIEWER_DIR / "index.html"

try:  # QtWebEngine vive en PySide6-Addons; si falta, la app sigue arrancando.
    from PySide6.QtWebEngineWidgets import QWebEngineView

    HAS_WEBENGINE = True
except ImportError:  # pragma: no cover - depende de la instalación
    QWebEngineView = None  # type: ignore[assignment]
    HAS_WEBENGINE = False


_STYLE = """
QMainWindow { background: #101620; }
QWidget { color: #d7dee8; }
QLabel#panelTitle {
    color: #7d8a9b; font-size: 11px; font-weight: 600;
    letter-spacing: 1px; padding: 2px 0 4px 2px;
}
QTreeWidget {
    background: #151a22; border: 1px solid #232c38; border-radius: 6px;
    alternate-background-color: #121821;
}
QTreeWidget::item { padding: 3px 2px; }
QTreeWidget::item:selected { background: #1f2b3a; color: #ffffff; }
QTabWidget::pane { border: 1px solid #232c38; border-radius: 6px; }
QTabBar::tab { background: transparent; color: #7d8a9b; padding: 6px 16px; }
QTabBar::tab:selected { color: #4cc9f0; border-bottom: 2px solid #4cc9f0; }
QPushButton {
    background: #1b2532; border: 1px solid #2b3746; border-radius: 6px;
    padding: 7px 12px;
}
QPushButton:hover { background: #22303f; border-color: #3a4c61; }
QPushButton:pressed { background: #4cc9f0; color: #0e1116; }
QPushButton:checked { border-color: #f7b32b; color: #f7b32b; }
QComboBox {
    background: #1b2532; border: 1px solid #2b3746; border-radius: 6px;
    padding: 4px 8px;
}
QComboBox QAbstractItemView {
    background: #1b2532; color: #d7dee8; border: 1px solid #2b3746;
    selection-background-color: #24313f;
}
QHeaderView { background: #151a22; }
QHeaderView::section {
    background: #151a22; color: #7d8a9b; border: none;
    border-bottom: 1px solid #232c38; padding: 4px 6px;
}
QToolTip { background: #1b2532; color: #d7dee8; border: 1px solid #2b3746; }
QWidget#panel {
    background: #101620; border: 1px solid #1a222d; border-radius: 8px;
}
QStatusBar { background: #0c1119; color: #7d8a9b; }
"""


def _make_panel() -> QWidget:
    """Panel lateral con tarjeta y borde visibles (evita confusión con fondos planos)."""
    panel = QWidget()
    panel.setObjectName("panel")
    return panel


class RigStudioWindow(QMainWindow):
    """Ventana principal con jerarquía, visor 3D y pestañas Rig/Simulación."""

    def __init__(self) -> None:
        super().__init__()
        # El estilo se aplica aquí (no en main()) para que la ventana se vea igual
        # cuando se instancia desde tests, sondas o el shim app/main_window.py.
        self.setStyleSheet(_STYLE)
        self.setWindowTitle("Rig Studio — Rigging & Simulation")
        self.resize(1440, 860)
        self._build_ui()

    # ------------------------------------------------------------------ montaje
    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_hierarchy_panel())
        splitter.addWidget(self._build_viewport_panel())
        splitter.addWidget(self._build_inspector_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([260, 900, 330])
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

        # `core_status()` nunca lanza: la ventana arranca aunque falte el núcleo y,
        # si la versión compilada no coincide con el proyecto, el texto ya trae la
        # orden para recompilar (RF-07 / CA-08).
        estado = core_status()
        visor = "WebEngine" if HAS_WEBENGINE else "no disponible"
        self.statusBar().showMessage(f"{estado.detail} · visor: {visor}")
        if estado.stale:
            self.statusBar().setStyleSheet("color: #f7b32b;")

    # 1) Panel izquierdo -------------------------------------------------------
    def _build_hierarchy_panel(self) -> QWidget:
        panel = _make_panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("JERARQUÍA")
        title.setObjectName("panelTitle")

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Elemento", "Tipo"])
        self._tree.setColumnWidth(0, 150)
        self._tree.setAlternatingRowColors(True)

        scene = QTreeWidgetItem(self._tree, ["Escena", "scene"])
        QTreeWidgetItem(scene, ["Cubo", "mesh"])
        skeleton = QTreeWidgetItem(scene, ["Esqueleto", "skeleton"])
        QTreeWidgetItem(skeleton, ["(sin joints)", "—"])
        scene.setExpanded(True)
        skeleton.setExpanded(True)

        layout.addWidget(title)
        layout.addWidget(self._tree, 1)
        return panel

    # 2) Panel central ---------------------------------------------------------
    def _build_viewport_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 10, 4, 10)
        layout.setSpacing(6)

        title = QLabel("VISOR 3D")
        title.setObjectName("panelTitle")

        self._view = self._make_viewer_widget()
        layout.addWidget(title)
        layout.addWidget(self._view, 1)
        return panel

    def _make_viewer_widget(self) -> QWidget:
        if not HAS_WEBENGINE:
            fallback = QTextBrowser()
            fallback.setHtml(
                "<h3>QtWebEngine no está disponible</h3>"
                "<p>Instala los addons de PySide6 para ver el visor:</p>"
                "<pre>pip install PySide6-Addons</pre>"
                f"<p>Mientras tanto puedes abrir <code>{VIEWER_HTML}</code> "
                "en un navegador (el visor no necesita servidor).</p>"
            )
            return fallback

        view = QWebEngineView()
        view.load(QUrl.fromLocalFile(str(VIEWER_HTML)))
        return view

    # 3) Panel derecho ---------------------------------------------------------
    def _build_inspector_panel(self) -> QWidget:
        panel = _make_panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tabs = QTabWidget()
        tabs.addTab(self._build_rig_tab(), "Rig")
        tabs.addTab(self._build_sim_tab(), "Simulación")
        layout.addWidget(tabs)
        return panel

    def _build_rig_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)

        preset = QComboBox()
        preset.addItems(["Bípedo simple", "Cuadrúpedo", "Caja (box)"])
        preset.setToolTip("Preset de esqueleto objetivo (placeholder)")

        generate = QPushButton("Generar esqueleto")
        generate.setDefault(True)
        # La conexión: señal clicked -> método Python que imprime en consola.
        generate.clicked.connect(self.on_generate_skeleton)

        frame = QPushButton("Encuadrar visor")
        frame.setToolTip("Llama a window.RigViewer.resetCamera() dentro del visor")
        frame.clicked.connect(self.on_frame_viewer)

        layout.addWidget(QLabel("Preset de esqueleto:"))
        layout.addWidget(preset)
        layout.addWidget(generate)
        layout.addWidget(frame)
        layout.addStretch(1)
        layout.addWidget(QLabel("Fase actual: esqueleto sin lógica de rigging."))
        return tab

    def _build_sim_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)

        start = QPushButton("▶ Iniciar simulación")
        start.clicked.connect(self.on_start_simulation)

        self._pause_button = QPushButton("⏸ Pausar visor")
        self._pause_button.setCheckable(True)
        # Signal clicked(bool checked) -> slot con parámetro bool.
        self._pause_button.clicked.connect(self.on_pause_toggled)

        layout.addWidget(start)
        layout.addWidget(self._pause_button)
        layout.addStretch(1)
        layout.addWidget(
            QLabel("Δt = 1/60 s · gravedad = −9.81 m/s²\n(placeholder: sin solver todavía)")
        )
        return tab

    # ------------------------------------------------------------------- slots
    @Slot()
    def on_generate_skeleton(self) -> None:
        """Demo mínima: solo imprime en la consola del proceso."""
        print("[rig] Generar esqueleto solicitado (demo, sin lógica todavía)")
        self.statusBar().showMessage("Rig · generar esqueleto (demo)")

    @Slot()
    def on_start_simulation(self) -> None:
        print("[sim] Iniciar simulación solicitado (demo, sin lógica todavía)")
        self.statusBar().showMessage("Simulación · iniciar (demo)")

    @Slot(bool)
    def on_pause_toggled(self, checked: bool) -> None:
        print(f"[sim] visor pausado = {checked}")
        valor_js = str(checked).lower()
        self._run_in_viewer(f"window.RigViewer && window.RigViewer.setPaused({valor_js});")
        self.statusBar().showMessage("Visor pausado" if checked else "Visor reanudado")

    @Slot()
    def on_frame_viewer(self) -> None:
        print("[viewer] resetCamera()")
        self._run_in_viewer("window.RigViewer && window.RigViewer.resetCamera();")

    # ------------------------------------------------------- Python -> JavaScript
    def _run_in_viewer(self, script: str) -> None:
        """Ejecuta JS en el visor (vía QtWebEngine). No-op si no hay WebEngine."""
        if not HAS_WEBENGINE:
            return
        page = self._view.page()
        page.runJavaScript(script, lambda result: None)


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Rig Studio")
    app.setOrganizationName("RigStudio")

    window = RigStudioWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

"""Compatibilidad: la ventana principal vive ahora en `app.main`.

Se mantiene este módulo para no romper imports previos (`from app.main_window
import MainWindow`). No añadas lógica aquí.
"""

from app.main import RigStudioWindow

MainWindow = RigStudioWindow

__all__ = ["MainWindow", "RigStudioWindow"]

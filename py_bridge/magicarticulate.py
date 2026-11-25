"""Adaptador para MagicArticulate (auto-rigging / skinning).

Este módulo **no** importa torch al cargarse: la UI debe poder abrirse en
máquinas sin GPU ni torch. La carga pesada ocurre en `MagicArticulateBackend.load()`.

Contrato previsto (a implementar en las tareas del plan SDD):
    vertices: np.ndarray[float32, (V, 3)]
    faces:    np.ndarray[int32,   (F, 3)]
    ->
    ArticulationResult(joints=(J, 3), skin_weights=(V, J), faces=(F, 3))
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PendingFeatureError(NotImplementedError):
    """Operación cuya implementación pertenece a una feature posterior.

    Hereda de ``NotImplementedError`` para conservar el contrato previo y para
    que la UI pueda distinguir «pendiente» de un fallo real (CA-33).
    """


_PENDING_MESSAGE = (
    "El auto-rigging con MagicArticulate todavía no está implementado: "
    "corresponde a la feature `magicarticulate-backend` (sidecar con venv propio). "
    "Ver specs/rig-studio-foundation/proposal.md §3, Decisión clave 1."
)


@dataclass(frozen=True, slots=True)
class ArticulationResult:
    """Resultado del auto-rigging."""

    joints: Any  # np.ndarray (J, 3) float32
    skin_weights: Any  # np.ndarray (V, J) float32
    faces: Any  # np.ndarray (F, 3) int32
    joint_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        joints = getattr(self.joints, "shape", None)
        weights = getattr(self.skin_weights, "shape", None)
        if joints is None or len(joints) != 2 or joints[1] != 3:
            raise ValueError("joints debe ser un array de forma (J, 3)")
        if weights is None or len(weights) != 2:
            raise ValueError("skin_weights debe ser un array de forma (V, J)")


class MagicArticulateBackend:
    """Envoltorio perezoso sobre el modelo MagicArticulate."""

    def __init__(self, weights_dir: Path | None = None, device: str | None = None) -> None:
        self.weights_dir = Path(weights_dir) if weights_dir else None
        self.device = device  # None => autodetectar (cuda > mps > cpu)
        self._model: Any | None = None

    # ------------------------------------------------------------------ estado
    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def torch_available(self) -> bool:
        """True si torch se puede importar (sin cargar el modelo)."""
        try:
            import torch  # noqa: F401, PLC0415 - import perezoso intencional
        except ImportError:
            return False
        return True

    def resolve_device(self) -> str:
        if self.device:
            return self.device
        if not self.torch_available():
            raise RuntimeError(
                "torch no está instalado: no se puede autodetectar el dispositivo. "
                "Instala requirements.txt o pasa device='cpu' explícitamente."
            )
        import torch  # noqa: PLC0415

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    # ------------------------------------------------------------------ modelo
    def load(self) -> None:
        """Carga pesos y modelo en memoria. Idempotente."""
        if self._model is not None:
            return
        if not self.torch_available():
            raise RuntimeError(
                "torch no está instalado. Instala requirements.txt "
                "(o la variante CUDA adecuada) antes de usar MagicArticulate."
            )
        # TODO(T-plan): cargar checkpoint desde self.weights_dir y moverlo a self.resolve_device()
        raise PendingFeatureError(_PENDING_MESSAGE)

    def articulate(self, vertices: Any, faces: Any) -> ArticulationResult:
        """Genera esqueleto + skinning para una malla."""
        if self._model is None:
            self.load()
        raise PendingFeatureError(_PENDING_MESSAGE)

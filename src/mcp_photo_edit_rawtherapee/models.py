"""Renderer-only models that adapt public contracts to an engine."""

from __future__ import annotations

from pathlib import Path

from mcp_photo_edit_core import (
    AdjustmentState as PublicAdjustmentState,
)
from mcp_photo_edit_core import (
    CropRect,
    DiagnosticDimensions,
    DiagnosticLumaSummary,
    DiagnosticRGBBalanceSummary,
    DiagnosticSaturationSummary,
    DiagnosticSummary,
    DocumentState,
    RGBMixer,
)
from mcp_photo_edit_core.models import OrientationDegrees
from pydantic import BaseModel


class AdjustmentState(PublicAdjustmentState):
    """Engine adapter state combining durable adjustments and geometry."""

    orientation: OrientationDegrees = 0
    crop: CropRect | None = None

    @classmethod
    def from_document(cls, document: DocumentState) -> AdjustmentState:
        """Build the engine view without leaking engine data into Document State."""

        data = document.adjustments.model_dump()
        data.update(document.geometry.model_dump())
        return cls.model_validate(data)


class SourceImageInfo(BaseModel):
    """Resolved local source information consumed by the renderer adapter."""

    input_path: str
    file_name: str
    suffix: str
    width: int | None = None
    height: int | None = None

    @classmethod
    def from_document(cls, source_path: Path, document: DocumentState) -> SourceImageInfo:
        """Resolve renderer input without changing durable source identity."""

        return cls(
            input_path=str(source_path),
            file_name=source_path.name,
            suffix=source_path.suffix.lower(),
            width=document.source.pixel_width,
            height=document.source.pixel_height,
        )


CropAdjustment = CropRect


__all__ = [
    "AdjustmentState",
    "CropAdjustment",
    "DiagnosticDimensions",
    "DiagnosticLumaSummary",
    "DiagnosticRGBBalanceSummary",
    "DiagnosticSaturationSummary",
    "DiagnosticSummary",
    "RGBMixer",
    "SourceImageInfo",
]

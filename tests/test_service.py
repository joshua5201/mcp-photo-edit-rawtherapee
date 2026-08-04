"""Tests for the typed in-process service boundary."""

from __future__ import annotations

from pathlib import Path

from mcp_photo_edit_core import (
    DocumentState,
    ErrorCode,
    RenderKind,
    RenderRequest,
    SourceAsset,
)

from mcp_photo_edit_rawtherapee.models import AdjustmentState, SourceImageInfo
from mcp_photo_edit_rawtherapee.service import RawEditService


class FakeRenderer:
    """Deterministic renderer used for service contract tests."""

    backend_id = "fake-renderer"
    state_file_name = "state.txt"
    supported_adjustment_names: tuple[str, ...] = ("exposure",)

    def ensure_available(self) -> None:
        return None

    def write_state_file(
        self,
        source: SourceImageInfo,
        adjustments: AdjustmentState,
        state_path: Path,
    ) -> None:
        state_path.write_text(f"{source.file_name}:{adjustments.exposure}", encoding="utf-8")

    def render_preview(
        self,
        source_path: Path,
        state_path: Path,
        target_path: Path,
        *,
        max_size: int | None = None,
    ) -> tuple[int, int] | None:
        del source_path, state_path, max_size
        target_path.write_bytes(b"preview")
        return (640, 480)

    def render_export(
        self,
        source_path: Path,
        state_path: Path,
        target_path: Path,
    ) -> tuple[int, int] | None:
        del source_path, state_path
        target_path.write_bytes(b"export")
        return (6000, 4000)


def request(tmp_path: Path, *, source_exists: bool = True) -> RenderRequest:
    """Build a valid render request."""

    source = tmp_path / "source.nef"
    if source_exists:
        source.write_bytes(b"raw")
    return RenderRequest(
        command_id="command-1",
        revision_id="revision-1",
        kind=RenderKind.PREVIEW,
        source_path=str(source),
        output_path=str(tmp_path / "preview.jpg"),
        preview_max_size=1024,
        document_state=DocumentState(
            document_id="document-1",
            source=SourceAsset(
                asset_id="asset-1",
                content_hash=f"sha256:{'a' * 64}",
                media_type="image/x-nikon-nef",
                pixel_width=6000,
                pixel_height=4000,
            ),
        ),
    )


def test_execute_returns_revision_bound_artifact(tmp_path: Path) -> None:
    service = RawEditService(FakeRenderer(), diagnostics_enabled=False)

    response = service.execute(request(tmp_path))

    assert response.error is None
    assert response.result is not None
    assert response.result.revision_id == "revision-1"
    assert response.result.artifact.width == 640
    assert Path(response.result.artifact.path).read_bytes() == b"preview"


def test_execute_maps_missing_source_to_validation_error(tmp_path: Path) -> None:
    service = RawEditService(FakeRenderer(), diagnostics_enabled=False)

    response = service.execute(request(tmp_path, source_exists=False))

    assert response.result is None
    assert response.error is not None
    assert response.error.code is ErrorCode.VALIDATION_ERROR


def test_capabilities_are_available_without_engine_executable() -> None:
    capabilities = RawEditService(FakeRenderer()).capabilities()

    assert capabilities.renderer.name == "fake-renderer"
    assert capabilities.render_kinds == [RenderKind.PREVIEW, RenderKind.EXPORT]

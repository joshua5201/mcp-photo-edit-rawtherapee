"""Synchronous in-process RAW edit service."""

from __future__ import annotations

import hashlib
import mimetypes
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import JsonValue
from raw_edit_contracts import (
    ErrorCode,
    ErrorEnvelope,
    FileArtifact,
    RenderCapabilities,
    RenderDiagnostics,
    RendererInfo,
    RenderKind,
    RenderRequest,
    RenderResult,
    ServiceResponse,
)

from .diagnostics import ImageDiagnostics
from .errors import BackendUnavailableError, PhotoEditError, ValidationError
from .models import AdjustmentState, SourceImageInfo
from .renderer import RawTherapeeBackend, RenderBackend


def _adapter_version() -> str:
    try:
        return version("raw-edit-service")
    except PackageNotFoundError:
        return "0.1.0"


class RawEditService:
    """Execute typed render requests using one injected renderer adapter."""

    def __init__(
        self,
        renderer: RenderBackend | None = None,
        *,
        diagnostics_enabled: bool = True,
    ) -> None:
        self.renderer = renderer or RawTherapeeBackend()
        self.diagnostics_enabled = diagnostics_enabled
        self._diagnostic_analyzer = ImageDiagnostics()

    def capabilities(self) -> RenderCapabilities:
        """Return stable capabilities without requiring the engine executable."""

        return RenderCapabilities(
            renderer=self._renderer_info(),
            render_kinds=[RenderKind.PREVIEW, RenderKind.EXPORT],
            supported_adjustments=list(self.renderer.supported_adjustment_names),
            output_media_types=["image/jpeg", "image/png", "image/tiff"],
        )

    def execute(self, request: RenderRequest) -> ServiceResponse:
        """Execute one request and map failures to the public error envelope."""

        try:
            return ServiceResponse(result=self._execute(request))
        except PhotoEditError as exc:
            return ServiceResponse(error=self._known_error(request.command_id, exc))
        except OSError as exc:
            return ServiceResponse(
                error=ErrorEnvelope(
                    code=ErrorCode.ASSET_UNAVAILABLE,
                    message=str(exc),
                    retriable=False,
                    command_id=request.command_id,
                )
            )
        except Exception as exc:  # boundary maps unexpected engine/library failures
            return ServiceResponse(
                error=ErrorEnvelope(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Unexpected render service failure: {exc}",
                    retriable=False,
                    command_id=request.command_id,
                )
            )

    def execute_or_raise(self, request: RenderRequest) -> RenderResult:
        """Execute for in-process callers that prefer Python exceptions."""

        response = self.execute(request)
        if response.result is not None:
            return response.result
        error = response.error
        if error is None:  # protected by ServiceResponse validation
            raise RuntimeError("render service returned no result or error")
        raise RuntimeError(f"{error.code}: {error.message}")

    def _execute(self, request: RenderRequest) -> RenderResult:
        source_path = Path(request.source_path).resolve()
        output_path = Path(request.output_path).resolve()
        if not source_path.is_file():
            raise ValidationError(f"Source file does not exist: {source_path}")

        source = SourceImageInfo.from_document(source_path, request.document_state)
        adjustments = AdjustmentState.from_document(request.document_state)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="raw-edit-state-", dir=output_path.parent
        ) as temp_dir:
            state_path = Path(temp_dir) / self.renderer.state_file_name
            self.renderer.write_state_file(source, adjustments, state_path)
            if request.kind is RenderKind.PREVIEW:
                size = self.renderer.render_preview(
                    source_path,
                    state_path,
                    output_path,
                    max_size=request.preview_max_size,
                )
            else:
                size = self.renderer.render_export(source_path, state_path, output_path)

        width, height = size if size is not None else (None, None)
        diagnostics = self._diagnostics(request, output_path)
        return RenderResult(
            command_id=request.command_id,
            asset_id=request.document_state.source.asset_id,
            revision_id=request.revision_id,
            kind=request.kind,
            artifact=FileArtifact(
                path=str(output_path),
                media_type=mimetypes.guess_type(output_path.name)[0] or "application/octet-stream",
                width=width,
                height=height,
                content_hash=_sha256(output_path),
            ),
            renderer=self._renderer_info(),
            diagnostics=diagnostics,
        )

    def _diagnostics(self, request: RenderRequest, output_path: Path) -> RenderDiagnostics | None:
        if not self.diagnostics_enabled:
            return None
        summary = self._diagnostic_analyzer.analyze(output_path)
        return RenderDiagnostics(
            asset_id=request.document_state.source.asset_id,
            revision_id=request.revision_id,
            summary=summary,
        )

    def _renderer_info(self) -> RendererInfo:
        return RendererInfo(
            name=self.renderer.backend_id,
            adapter_version=_adapter_version(),
        )

    @staticmethod
    def _known_error(command_id: str, exc: PhotoEditError) -> ErrorEnvelope:
        if isinstance(exc, BackendUnavailableError):
            code = ErrorCode.BACKEND_UNAVAILABLE
        elif isinstance(exc, ValidationError):
            code = ErrorCode.VALIDATION_ERROR
        else:
            code = ErrorCode.RENDER_FAILED
        details: dict[str, JsonValue] = {"hint": exc.hint} if exc.hint is not None else {}
        return ErrorEnvelope(
            code=code,
            message=exc.message,
            retriable=code is ErrorCode.BACKEND_UNAVAILABLE,
            command_id=command_id,
            details=details,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"

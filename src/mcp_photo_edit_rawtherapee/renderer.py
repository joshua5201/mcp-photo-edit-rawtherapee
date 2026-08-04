"""Typed RawTherapee renderer adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from PIL import Image

from .errors import BackendUnavailableError, RenderFailedError, ValidationError
from .models import AdjustmentState, SourceImageInfo
from .pp3 import build_pp3

RAWTHERAPEE_CLI_ENV = "RAWTHERAPEE_CLI"


class RenderBackend(Protocol):
    """Internal engine adapter consumed by the service boundary."""

    backend_id: str
    state_file_name: str
    supported_adjustment_names: tuple[str, ...]

    def ensure_available(self) -> None: ...

    def write_state_file(
        self,
        source: SourceImageInfo,
        adjustments: AdjustmentState,
        state_path: Path,
    ) -> None: ...

    def render_preview(
        self,
        source_path: Path,
        state_path: Path,
        target_path: Path,
        *,
        max_size: int | None = None,
    ) -> tuple[int, int] | None: ...

    def render_export(
        self,
        source_path: Path,
        state_path: Path,
        target_path: Path,
    ) -> tuple[int, int] | None: ...


class RawTherapeeBackend:
    """Render previews and exports through `rawtherapee-cli`."""

    backend_id: str = "rawtherapee-cli"
    state_file_name: str = "session.pp3"
    supported_adjustment_names: tuple[str, ...] = (
        "exposure",
        "contrast",
        "saturation",
        "rgb_mixer",
        "denoise_luma",
        "denoise_detail",
        "denoise_chroma",
        "color_temperature",
        "green_balance",
        "highlights",
        "shadows",
        "sharpen_amount",
        "sharpen_radius",
        "sharpen_contrast",
        "orientation",
        "crop",
    )

    def __init__(
        self,
        executable: str = "rawtherapee-cli",
        *,
        preview_quality: int = 70,
        export_quality: int = 92,
    ) -> None:
        self.executable = executable
        self.preview_quality = preview_quality
        self.export_quality = export_quality

    def ensure_available(self) -> None:
        self._resolve_executable()

    def write_state_file(
        self,
        source: SourceImageInfo,
        adjustments: AdjustmentState,
        state_path: Path,
    ) -> None:
        self._validate_adjustments(adjustments, source)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            build_pp3(adjustments, image_width=source.width, image_height=source.height),
            encoding="utf-8",
        )

    def render_preview(
        self,
        source_path: Path,
        state_path: Path,
        target_path: Path,
        *,
        max_size: int | None = None,
    ) -> tuple[int, int] | None:
        executable = self._resolve_executable()
        target_path = target_path.resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="rawtherapee-preview-", dir=target_path.parent
        ) as temp_dir:
            temporary_output = Path(temp_dir) / target_path.name
            self._render(
                source_path,
                state_path,
                temporary_output,
                executable=executable,
                quality=self.preview_quality,
            )
            rendered_size = _image_dimensions(temporary_output)
            if max_size is None:
                temporary_output.replace(target_path)
            else:
                self._resize_preview(temporary_output, target_path, max_size=max_size)
        self._require_output(target_path)
        return rendered_size

    def render_export(
        self,
        source_path: Path,
        state_path: Path,
        target_path: Path,
    ) -> tuple[int, int] | None:
        executable = self._resolve_executable()
        target_path = target_path.resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self._render(
            source_path,
            state_path,
            target_path,
            executable=executable,
            quality=self.export_quality,
        )
        return _image_dimensions(target_path)

    def _render(
        self,
        source_path: Path,
        state_path: Path,
        target_path: Path,
        *,
        executable: str,
        quality: int,
    ) -> None:
        command = [
            executable,
            "-o",
            str(target_path),
            "-Y",
            *self._output_args(target_path, quality),
            "-p",
            str(state_path),
            "-c",
            str(source_path),
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            details = "\n".join(
                part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
            )
            raise RenderFailedError(
                f"{executable} exited with status {completed.returncode}.",
                hint=details or None,
            )
        self._require_output(target_path)

    def _resolve_executable(self) -> str:
        path_executable = shutil.which(self.executable)
        if path_executable is not None:
            return path_executable

        configured = os.environ.get(RAWTHERAPEE_CLI_ENV)
        if configured is None or not configured.strip():
            raise BackendUnavailableError(
                self.executable,
                hint=(
                    f"Install {self.executable} on PATH or set {RAWTHERAPEE_CLI_ENV} "
                    "to the absolute executable path."
                ),
            )

        candidate = Path(configured)
        if not candidate.is_absolute():
            raise BackendUnavailableError(
                self.executable,
                hint=f"{RAWTHERAPEE_CLI_ENV} must be an absolute path; got '{configured}'.",
            )
        if not candidate.is_file():
            raise BackendUnavailableError(
                self.executable,
                hint=f"{RAWTHERAPEE_CLI_ENV} does not point to an existing file: '{configured}'.",
            )
        return str(candidate)

    def _output_args(self, target_path: Path, quality: int) -> list[str]:
        suffix = target_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            return [f"-j{quality}"]
        if suffix == ".png":
            return ["-n"]
        if suffix in {".tif", ".tiff"}:
            return ["-t"]
        raise ValidationError(
            f"Unsupported export format '{suffix or '<none>'}' for {self.backend_id}.",
            hint="Use .jpg, .jpeg, .png, .tif, or .tiff outputs.",
        )

    def _validate_adjustments(self, adjustments: AdjustmentState, source: SourceImageInfo) -> None:
        if adjustments.crop is not None and (source.width is None or source.height is None):
            raise ValidationError(
                f"Adjustments not yet supported by {self.backend_id}: crop.",
                hint=(
                    "Create a session preview first so the backend can determine "
                    "the developed image dimensions."
                ),
            )

    def _require_output(self, target_path: Path) -> None:
        if not target_path.exists():
            raise RenderFailedError(
                f"{self.executable} completed without producing '{target_path.name}'.",
                hint=(
                    "Inspect backend output and verify the source file, PP3 profile, "
                    "and output format."
                ),
            )

    def _resize_preview(self, source_path: Path, target_path: Path, *, max_size: int) -> None:
        with Image.open(source_path) as source_image:
            image = source_image.copy()
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        image.save(target_path, quality=self.preview_quality, optimize=True)


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as image:
            return image.size
    except OSError:
        return None


def build_backend_registry() -> dict[str, RenderBackend]:
    """Return the default renderer registry."""

    renderer: RenderBackend = RawTherapeeBackend()
    return {renderer.backend_id: renderer}

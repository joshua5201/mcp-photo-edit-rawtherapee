"""RawTherapee renderer adapter tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch

from raw_edit_service.models import AdjustmentState, CropAdjustment, SourceImageInfo
from raw_edit_service.renderer import RawTherapeeBackend


def test_render_invokes_rawtherapee_with_pp3(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def fake_which(name: str) -> str:
        assert name == "rawtherapee-cli"
        return "C:/tools/rawtherapee-cli.exe"

    def fake_run(
        command: list[str], check: bool, capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, text
        commands.append(command)
        output_path = Path(command[2])
        output_path.write_bytes(b"jpg")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("raw_edit_service.renderer.shutil.which", fake_which)
    monkeypatch.setattr("raw_edit_service.renderer.subprocess.run", fake_run)
    source = tmp_path / "source.nef"
    profile = tmp_path / "session.pp3"
    target = tmp_path / "preview.jpg"
    source.write_bytes(b"raw")
    profile.write_text("[Exposure]\n", encoding="utf-8")

    RawTherapeeBackend().render_preview(source, profile, target)

    assert target.read_bytes() == b"jpg"
    assert commands[0][0] == "rawtherapee-cli"
    assert "-p" in commands[0]


def test_render_rejects_missing_output(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str:
        del name
        return "C:/tools/rawtherapee-cli.exe"

    def fake_run(
        command: list[str], check: bool, capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, text
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("raw_edit_service.renderer.shutil.which", fake_which)
    monkeypatch.setattr("raw_edit_service.renderer.subprocess.run", fake_run)
    source = tmp_path / "source.nef"
    profile = tmp_path / "session.pp3"
    source.write_bytes(b"raw")
    profile.write_text("[Exposure]\n", encoding="utf-8")

    with pytest.raises(Exception, match="without producing"):
        RawTherapeeBackend().render_export(source, profile, tmp_path / "export.jpg")


def test_state_file_requires_dimensions_for_crop(tmp_path: Path) -> None:
    source = SourceImageInfo(
        input_path=str(tmp_path / "source.nef"),
        file_name="source.nef",
        suffix=".nef",
    )

    with pytest.raises(Exception, match="crop"):
        RawTherapeeBackend().write_state_file(
            source,
            AdjustmentState(crop=CropAdjustment(left=0.1, top=0.1, right=0.9, bottom=0.9)),
            tmp_path / "state.pp3",
        )

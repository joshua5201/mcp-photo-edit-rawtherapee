"""RawTherapee renderer adapter tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch

from raw_edit_service.errors import BackendUnavailableError
from raw_edit_service.models import AdjustmentState, CropAdjustment, SourceImageInfo
from raw_edit_service.renderer import RAWTHERAPEE_CLI_ENV, RawTherapeeBackend


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
    assert commands[0][0] == "C:/tools/rawtherapee-cli.exe"
    assert "-p" in commands[0]


def test_path_takes_precedence_over_environment(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    path_executable = "C:/path/rawtherapee-cli.exe"
    environment_executable = tmp_path / "environment" / "rawtherapee-cli.exe"
    environment_executable.parent.mkdir()
    environment_executable.write_bytes(b"exe")
    monkeypatch.setenv(RAWTHERAPEE_CLI_ENV, str(environment_executable))

    def fake_which(name: str) -> str:
        assert name == "rawtherapee-cli"
        return path_executable

    monkeypatch.setattr("raw_edit_service.renderer.shutil.which", fake_which)

    backend = RawTherapeeBackend()

    backend.ensure_available()


def test_absolute_environment_path_is_fallback(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    environment_executable = tmp_path / "RawTherapee" / "rawtherapee-cli.exe"
    environment_executable.parent.mkdir()
    environment_executable.write_bytes(b"exe")
    monkeypatch.setenv(RAWTHERAPEE_CLI_ENV, str(environment_executable))

    def fake_which(name: str) -> None:
        assert name == "rawtherapee-cli"

    monkeypatch.setattr("raw_edit_service.renderer.shutil.which", fake_which)

    backend = RawTherapeeBackend()

    backend.ensure_available()


@pytest.mark.parametrize("configured", ["rawtherapee-cli.exe", "missing/rawtherapee-cli.exe"])
def test_environment_path_must_be_absolute(monkeypatch: MonkeyPatch, configured: str) -> None:
    monkeypatch.setenv(RAWTHERAPEE_CLI_ENV, configured)

    def fake_which(name: str) -> None:
        assert name == "rawtherapee-cli"

    monkeypatch.setattr("raw_edit_service.renderer.shutil.which", fake_which)

    with pytest.raises(BackendUnavailableError) as error:
        RawTherapeeBackend().ensure_available()

    assert error.value.hint is not None
    assert "must be an absolute path" in error.value.hint


def test_environment_path_must_point_to_a_file(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    missing_executable = tmp_path / "missing" / "rawtherapee-cli.exe"
    monkeypatch.setenv(RAWTHERAPEE_CLI_ENV, str(missing_executable))

    def fake_which(name: str) -> None:
        assert name == "rawtherapee-cli"

    monkeypatch.setattr("raw_edit_service.renderer.shutil.which", fake_which)

    with pytest.raises(BackendUnavailableError) as error:
        RawTherapeeBackend().ensure_available()

    assert error.value.hint is not None
    assert "does not point to an existing file" in error.value.hint


def test_missing_path_and_environment_reports_both_options(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv(RAWTHERAPEE_CLI_ENV, raising=False)

    def fake_which(name: str) -> None:
        assert name == "rawtherapee-cli"

    monkeypatch.setattr("raw_edit_service.renderer.shutil.which", fake_which)

    with pytest.raises(BackendUnavailableError) as error:
        RawTherapeeBackend().ensure_available()

    assert error.value.hint is not None
    assert RAWTHERAPEE_CLI_ENV in error.value.hint


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

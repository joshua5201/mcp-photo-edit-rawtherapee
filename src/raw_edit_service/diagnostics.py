"""Typed diagnostics for a rendered RGB artifact."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

from PIL import Image
from raw_edit_contracts import (
    DiagnosticDimensions,
    DiagnosticLumaSummary,
    DiagnosticRGBBalanceSummary,
    DiagnosticSaturationSummary,
    DiagnosticSummary,
)

RGBPixel = tuple[int, int, int]


class _RGBBytes(Protocol):
    """Narrow Pillow adapter boundary used by the strict domain layer."""

    def tobytes(self, encoder_name: str = "raw") -> bytes: ...


class ImageDiagnostics:
    """Compute the M0 metrics from the exact rendered image."""

    def analyze(self, image_path: Path) -> DiagnosticSummary:
        with Image.open(image_path) as source_image:
            image = source_image.convert("RGB")
        raw_pixels = cast(_RGBBytes, image).tobytes()
        pixels: list[RGBPixel] = [
            (raw_pixels[index], raw_pixels[index + 1], raw_pixels[index + 2])
            for index in range(0, len(raw_pixels), 3)
        ]
        if not pixels:
            raise ValueError("cannot analyze an empty rendered image")

        luma_values: list[float] = []
        saturation_values: list[float] = []
        red_total = 0
        green_total = 0
        blue_total = 0
        for red, green, blue in pixels:
            red_total += red
            green_total += green
            blue_total += blue
            luma_values.append(0.2126 * red + 0.7152 * green + 0.0722 * blue)
            saturation_values.append(_saturation(red, green, blue))

        luma_values.sort()
        saturation_values.sort()
        count = len(pixels)
        red_mean = red_total / count
        green_mean = green_total / count
        blue_mean = blue_total / count
        return DiagnosticSummary(
            dimensions=DiagnosticDimensions(width=image.width, height=image.height),
            luma=DiagnosticLumaSummary(
                p01=_percentile(luma_values, 0.01),
                p50=_percentile(luma_values, 0.50),
                p99=_percentile(luma_values, 0.99),
                clipped_black_pct=100.0 * sum(value <= 1.0 for value in luma_values) / count,
                clipped_white_pct=100.0 * sum(value >= 254.0 for value in luma_values) / count,
            ),
            rgb_balance=DiagnosticRGBBalanceSummary(
                red_mean=red_mean,
                green_mean=green_mean,
                blue_mean=blue_mean,
                temperature_hint=_temperature_hint(red_mean, blue_mean),
                tint_hint=_tint_hint(red_mean, green_mean, blue_mean),
            ),
            saturation=DiagnosticSaturationSummary(
                p50=_percentile(saturation_values, 0.50),
                p95=_percentile(saturation_values, 0.95),
                high_saturation_pct=(
                    100.0 * sum(value >= 75.0 for value in saturation_values) / count
                ),
            ),
        )


def _percentile(values: list[float], fraction: float) -> float:
    index = round((len(values) - 1) * fraction)
    return values[index]


def _saturation(red: int, green: int, blue: int) -> float:
    high = max(red, green, blue)
    low = min(red, green, blue)
    return 0.0 if high == 0 else 100.0 * (high - low) / high


def _temperature_hint(red: float, blue: float) -> str:
    difference = red - blue
    if difference > 8.0:
        return "warm"
    if difference < -8.0:
        return "cool"
    return "balanced"


def _tint_hint(red: float, green: float, blue: float) -> str:
    reference = (red + blue) / 2.0
    difference = green - reference
    if difference > 8.0:
        return "green"
    if difference < -8.0:
        return "magenta"
    return "balanced"

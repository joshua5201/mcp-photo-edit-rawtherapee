"""JSON command-line transport for the synchronous service."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcp_photo_edit_core import RenderRequest

from .service import RawEditService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute a typed RAW render request")
    parser.add_argument(
        "request",
        nargs="?",
        type=Path,
        help="JSON request file; omit to read UTF-8 JSON from stdin",
    )
    return parser


def main() -> None:
    """Read one request and print one ServiceResponse JSON document."""

    args = _parser().parse_args()
    request_path = args.request
    payload = request_path.read_text(encoding="utf-8") if request_path else sys.stdin.read()
    request = RenderRequest.model_validate_json(payload)
    response = RawEditService().execute(request)
    sys.stdout.write(response.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()

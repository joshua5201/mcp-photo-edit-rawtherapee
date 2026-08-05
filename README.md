# mcp-photo-edit-rawtherapee

RawTherapee implementation behind the public `mcp-photo-edit-core` models. The
same synchronous service can be called directly in-process or through a small JSON
CLI boundary.

RawTherapee is the first renderer. The executable is resolved in this order:

1. use `rawtherapee-cli` when it is available on `PATH`;
2. otherwise use the absolute executable path in `RAWTHERAPEE_CLI`;
3. otherwise return a structured `BACKEND_UNAVAILABLE` error.

Windows PowerShell example when RawTherapee is installed but not on `PATH`:

```powershell
$env:RAWTHERAPEE_CLI = "C:\Program Files\RawTherapee\5.12\rawtherapee-cli.exe"
mcp-photo-edit-rawtherapee request.json
```

Relative values and paths that do not point to an existing file are rejected.

```python
from mcp_photo_edit_rawtherapee import RawEditService

response = RawEditService().execute(request)
```

```shell
mcp-photo-edit-rawtherapee request.json
```

Development gates:

```shell
uv sync --frozen --group dev
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen basedpyright
uv run --frozen pytest
uv build --no-sources
```

Development and CI require uv `0.11.32`; the checked-in `uv.lock` resolves only
published dependencies (the project itself is the expected editable root entry).

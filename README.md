# raw-edit-service

RAW rendering implementation behind the public `raw-edit-contracts` models. The
same synchronous service can be called directly in-process or through a small JSON
CLI boundary.

RawTherapee is the first renderer. The executable is resolved in this order:

1. use `rawtherapee-cli` when it is available on `PATH`;
2. otherwise use the absolute executable path in `RAWTHERAPEE_CLI`;
3. otherwise return a structured `BACKEND_UNAVAILABLE` error.

Windows PowerShell example when RawTherapee is installed but not on `PATH`:

```powershell
$env:RAWTHERAPEE_CLI = "C:\Program Files\RawTherapee\5.12\rawtherapee-cli.exe"
raw-edit-service request.json
```

Relative values and paths that do not point to an existing file are rejected.

```python
from raw_edit_service import RawEditService

response = RawEditService().execute(request)
```

```shell
raw-edit-service request.json
```

Development gates:

```shell
uv sync
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run pytest
uv run python -m build
```

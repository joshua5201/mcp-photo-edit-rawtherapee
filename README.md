# raw-edit-service

RAW rendering implementation behind the public `raw-edit-contracts` models. The
same synchronous service can be called directly in-process or through a small JSON
CLI boundary.

RawTherapee is the first renderer. Install `rawtherapee-cli` and make it available
on `PATH` before requesting a real render.

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

"""
生产环境：托管 admin-ui 构建产物（SPA）。
开发时无 dist 目录则跳过，继续走 Vite 5173。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_RESERVED_PREFIXES = ("api/", "auth/")
_RESERVED_EXACT = frozenset({"health", "docs", "openapi.json", "redoc"})


def register_spa_static(app, *, repo_root: Path) -> bool:
    dist = (repo_root / "admin-ui" / "dist").resolve()
    index = dist / "index.html"
    if not index.is_file():
        return False

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="spa-assets")

    for name in ("favicon.svg",):
        file_path = dist / name
        if file_path.is_file():

            def _make_handler(path: Path = file_path):
                async def _handler():
                    return FileResponse(path)
                return _handler

            app.add_api_route(f"/{name}", _make_handler(), methods=["GET"], include_in_schema=False)

    @app.get("/", include_in_schema=False)
    async def spa_root():
        return FileResponse(index)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if any(full_path.startswith(prefix) for prefix in _RESERVED_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")
        head = full_path.split("/", 1)[0] if full_path else ""
        if head in _RESERVED_EXACT or full_path in _RESERVED_EXACT:
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not Found") from None
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return True

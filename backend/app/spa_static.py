from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            response = None
        if response is not None and response.status_code != 404:
            return response
        normalized = path.lstrip("/")
        reserved = (
            normalized == "api"
            or normalized.startswith("api/")
            or normalized in {"docs", "redoc"}
        )
        if reserved:
            if response is not None:
                return response
            raise HTTPException(status_code=404)
        if scope.get("method") in {"GET", "HEAD"} and "." not in path.rsplit("/", 1)[-1]:
            return await super().get_response("index.html", scope)
        if response is not None:
            return response
        raise HTTPException(status_code=404)

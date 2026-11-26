"""Diagnostics use model metadata only. Opening the settings panel performs no external I/O."""
import asyncio
from time import monotonic

import httpx
from fastapi import APIRouter, HTTPException

from .provider_config import (LOCAL_MODEL, PROVIDERS, ProviderError, ProviderName, default_model,
                              default_provider, endpoint, valid_model)
from .provider_stream import read_json
from .providers import http_error

router = APIRouter(prefix="/api/providers")
METADATA_TIMEOUT = 8


def configured(name):
    if name == "mock":
        return True
    try:
        endpoint(name)
    except ProviderError:
        return False
    return True


@router.get("")
def settings():
    try:
        default = default_provider()
    except ProviderError:
        default = None
    return {"default_provider": default,
            "providers": [{"id": name, "configured": configured(name), "default_model": default_model(name)}
                          for name in PROVIDERS]}


async def list_models(name, *, transport=None):
    if name == "mock":
        return [LOCAL_MODEL], False
    base, headers = endpoint(name)
    url = base + ("/api/tags" if name == "ollama" else "/models")
    try:
        async with asyncio.timeout(METADATA_TIMEOUT), httpx.AsyncClient(
            transport=transport, timeout=httpx.Timeout(4, connect=2), follow_redirects=False
        ) as client:
            # Retry once for transient failures on the read-only catalog operation.
            for attempt in range(2):
                try:
                    async with client.stream("GET", url, headers=headers) as response:
                        if not attempt and response.status_code in {502, 503, 504}:
                            continue
                        if not response.is_success:
                            raise http_error(response.status_code)
                        body = await read_json(response)
                        break
                except (httpx.NetworkError, httpx.TimeoutException):
                    if attempt:
                        raise
        rows = body["models" if name == "ollama" else "data"]
        if not isinstance(rows, list):
            raise ValueError
        models = []
        for row in rows[:1000]:
            model = row["name" if name == "ollama" else "id"]
            if valid_model(model):
                models.append(model)
        return sorted(set(models)), bool(body.get("has_more") or len(rows) > 1000)
    except (httpx.TimeoutException, TimeoutError):
        raise ProviderError("모델 목록 응답 시간이 초과되었습니다.") from None
    except (httpx.HTTPError, httpx.InvalidURL):
        raise http_error(0) from None
    except (TypeError, KeyError, ValueError, AttributeError, RecursionError):
        raise ProviderError("공급자의 모델 목록을 읽을 수 없습니다. 모델 ID를 직접 입력할 수 있습니다.") from None


async def diagnostics(name, include_models):
    started = monotonic()
    try:
        found, partial = await list_models(name)
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from None
    result = {"provider": name, "reachable": True, "count": len(found), "partial": partial,
              "latency_ms": round((monotonic() - started) * 1000)}
    if include_models:
        result["models"] = found
    return result


@router.get("/{provider}/models")
async def models(provider: ProviderName):
    return await diagnostics(provider, include_models=True)


@router.post("/{provider}/probe")
async def probe(provider: ProviderName):
    return await diagnostics(provider, include_models=False)

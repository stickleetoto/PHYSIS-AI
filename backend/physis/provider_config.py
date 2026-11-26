"""Server-owned destinations, request-local selection and credential-free telemetry."""
import ipaddress
import os
import re
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator

from .schema import StrictModel

ProviderName = Literal["mock", "openai", "anthropic", "ollama", "compatible"]
PROVIDERS = ("mock", "openai", "anthropic", "ollama", "compatible")
LOCAL_MODEL = "local-rules"
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+@:/-]{0,199}\Z")
KEY_VARS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PHYSIS_COMPATIBLE_API_KEY")
ENV_DEFAULT_OPT_IN = "PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT"


class ProviderError(Exception):
    """A public error suitable for the HTTP API."""


def valid_model(model) -> bool:
    if not isinstance(model, str) or not MODEL_ID.fullmatch(model):
        return False
    return not any(key and key in model for key in (os.getenv(k, "").strip() for k in KEY_VARS))


class ProviderSelection(StrictModel):
    provider: ProviderName
    model: str

    @field_validator("model")
    @classmethod
    def check_model_id(cls, model):
        if not valid_model(model):
            raise ValueError("올바른 모델 ID를 입력하세요.")
        return model

    @model_validator(mode="after")
    def check_local_model(self):
        if self.provider == "mock" and self.model != LOCAL_MODEL:
            raise ValueError("Mock 공급자의 모델 ID는 local-rules입니다.")
        return self


def default_provider() -> str:
    name = os.getenv("PHYSIS_AI_PROVIDER", "mock").strip().lower()
    if name not in PROVIDERS:
        raise ProviderError("PHYSIS_AI_PROVIDER 설정을 확인하세요.")
    # Credentials and a configured endpoint are not consent to spend money or
    # start local inference. Environment-only live defaults require a separate,
    # explicit opt-in; a request-local ProviderSelection remains deliberate.
    if name != "mock" and os.getenv(ENV_DEFAULT_OPT_IN) != "1":
        return "mock"
    return name


def default_model(name):
    if name == "mock":
        return LOCAL_MODEL
    model = os.getenv(f"PHYSIS_{name.upper()}_MODEL", "").strip()
    if not model and name == os.getenv("PHYSIS_AI_PROVIDER", "mock").strip().lower():
        model = os.getenv("PHYSIS_AI_MODEL", "").strip()
    return model if valid_model(model) else ""


def required(var):
    value = os.getenv(var, "").strip()
    if not value:
        raise ProviderError(f"서버에 {var} 설정이 필요합니다.")
    return value


def endpoint(name):
    """Only server configuration can determine the URL and credential recipient."""
    if os.getenv("PHYSIS_OFFLINE") == "1" and name != "mock":
        raise ProviderError("오프라인 실행에서는 로컬 Mock을 사용하세요.")
    headers = {"Accept-Encoding": "identity"}
    if name == "openai":
        headers["Authorization"] = "Bearer " + required("OPENAI_API_KEY")
        return "https://api.openai.com/v1", headers
    if name == "anthropic":
        headers.update({"x-api-key": required("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"})
        return "https://api.anthropic.com/v1", headers
    if name == "ollama":
        url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
    elif name == "compatible":
        url = required("PHYSIS_COMPATIBLE_BASE_URL")
        key = os.getenv("PHYSIS_COMPATIBLE_API_KEY", "").strip()
        if key:
            headers["Authorization"] = "Bearer " + key
    else:
        raise ProviderError("지원하는 AI 공급자를 선택하세요.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
        if (not host or parts.scheme not in {"https", "http"} or port == 0
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or any(c.isspace() or c == "\\" for c in url)):
            raise ValueError
        if "Authorization" in headers and parts.scheme == "http" and host != "localhost":
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError
    except ValueError:
        raise ProviderError("서버의 공급자 URL을 확인하세요. 원격 인증 연결에는 HTTPS가 필요합니다.") from None
    return url.rstrip("/"), headers


@dataclass
class ProviderMetrics:
    provider: str
    model: str
    requests: list[dict] = field(default_factory=list)
    visual_actions: list[dict] = field(default_factory=list, repr=False)
    research_context: dict = field(default_factory=dict, repr=False)
    proposed_sources: list[str] = field(default_factory=list, repr=False)
    proposed_numbers: list[dict] = field(default_factory=list, repr=False)
    started: float = field(default_factory=monotonic)
    elapsed_ms: int | None = None

    def as_dict(self):
        elapsed = self.elapsed_ms if self.elapsed_ms is not None else round((monotonic() - self.started) * 1000)
        return {"provider": self.provider, "model": self.model, "requests": self.requests.copy(), "latency_ms": elapsed}


@dataclass
class RequestContext:
    metrics: ProviderMetrics
    stream: bool
    on_progress: Callable[[dict], None] | None


current_context: ContextVar[RequestContext | None] = ContextVar("physis_provider", default=None)


def provider_name():
    ctx = current_context.get()
    return ctx.metrics.provider if ctx else default_provider()


def model_for(name):
    ctx = current_context.get()
    if ctx is not None:
        if name != ctx.metrics.provider:
            raise ProviderError("요청의 AI 공급자가 일치하지 않습니다.")
        return ctx.metrics.model
    model = default_model(name) or required("PHYSIS_AI_MODEL")
    if not valid_model(model):
        raise ProviderError("서버의 모델 ID를 확인하세요.")
    return model


@contextmanager
def provider_context(selection: ProviderSelection | None = None, *, stream=False, on_progress=None):
    if selection is None:
        name = default_provider()
        model = default_model(name)
        if not model:
            raise ProviderError("서버에 PHYSIS_AI_MODEL을 설정하거나 모델 ID를 선택하세요.")
    else:
        name, model = selection.provider, selection.model
    metrics = ProviderMetrics(name, model)
    token = current_context.set(RequestContext(metrics, stream, on_progress))
    try:
        yield metrics
    finally:
        current_context.reset(token)
        metrics.elapsed_ms = round((monotonic() - metrics.started) * 1000)

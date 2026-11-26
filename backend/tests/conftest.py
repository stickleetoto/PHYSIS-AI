"""Keep backend tests on in-process adapters, including when developer keys are configured."""
import httpx
import pytest

_app_servers = set()


@pytest.fixture
def allow_fixture_server():
    """Allow only the exact loopback port opened by a network-level app test."""
    def register(listener):
        host, port = listener.getsockname()
        assert host == "127.0.0.1" and port > 0
        _app_servers.add((host, port))
    yield register
    _app_servers.clear()


@pytest.fixture(autouse=True, scope="session")
def no_real_http_transports():
    def reject(_transport, _request):
        raise AssertionError("Live HTTP is disabled in backend tests. Inject a Mock or Replay provider.")

    original_async = httpx.AsyncHTTPTransport.handle_async_request
    async def reject_async(transport, request):
        if (request.url.host, request.url.port) in _app_servers:
            return await original_async(transport, request)
        reject(transport, request)

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PYTHON_DOTENV_DISABLED", "1")
        patch.setattr(httpx.HTTPTransport, "handle_request", reject)
        patch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_async)
        yield

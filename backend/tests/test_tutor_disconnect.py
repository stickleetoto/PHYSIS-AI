"""A real client disconnect must cancel pending interpretation before any write."""
import asyncio
import socket

import httpx
import uvicorn

from physis import reasoning
from physis.api import create_app


def test_client_disconnect_cancels_tutor_and_preserves_revision(tmp_path, monkeypatch, allow_fixture_server):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "mock")

    async def scenario():
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def slow_interpret(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        monkeypatch.setattr(reasoning, "interpret", slow_interpret)
        app = create_app(tmp_path / "disconnect.db")
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", ws="none"))
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            allow_fixture_server(listener)
            address = "http://127.0.0.1:" + str(listener.getsockname()[1])
            task = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(10):
                    while not server.started:
                        await asyncio.sleep(.02)
                    async with httpx.AsyncClient(base_url=address, trust_env=False) as client:
                        start = (await client.post("/api/experiments", json={"model": "free_fall"})).json()
                        eid = start["experiment"]["id"]
                        question = {"experiment_id": eid, "revision": 1, "message": "출발 높이를 5 m로 변경해 줘"}
                        async with client.stream("POST", "/api/tutor/stream", json=question) as stream:
                            stream.raise_for_status()
                            lines = stream.aiter_lines()
                            assert '"stage"' in await anext(lines)
                            await entered.wait()
                        await cancelled.wait()
                        while not (usage := (await client.get("/api/usage")).json()["items"]):
                            await asyncio.sleep(.02)
                        assert usage[0]["outcome"] == "cancelled"
                        assert (await client.get("/api/experiments/" + eid)).json() == start
            finally:
                server.should_exit = True
                await asyncio.wait_for(task, 5)

    asyncio.run(scenario())

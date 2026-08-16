"""Async WebSocket client for the Deriv Options API.

Requests are correlated to responses via `req_id` through a background reader
task, rather than a naive send-then-recv on the socket. A naive recv() breaks
as soon as anything else reads from the same connection concurrently (e.g. a
background contract-monitoring task alongside the main scan loop) -- see
docs/postmortem/PROJECT_POSTMORTEM.md item 14 for the class of bug this
avoids.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging

import websockets

from quantum_tick.infrastructure.deriv.exceptions import DerivApiError

log = logging.getLogger("quantum_tick.deriv.client")

DEFAULT_TIMEOUT = 20.0


class DerivClient:
    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._req_id = itertools.count(1)
        self._reader_task: asyncio.Task | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._ws_url, ping_interval=20, ping_timeout=20)
        self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def __aenter__(self) -> "DerivClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                req_id = msg.get("req_id")
                fut = self._pending.pop(req_id, None) if req_id is not None else None
                if fut is not None and not fut.done():
                    fut.set_result(msg)
        except websockets.exceptions.ConnectionClosed as exc:
            self._fail_all_pending(exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface unexpected reader errors to callers
            self._fail_all_pending(exc)

    def _fail_all_pending(self, exc: Exception) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()

    async def request(self, payload: dict, timeout: float = DEFAULT_TIMEOUT) -> dict:
        if self._ws is None:
            raise RuntimeError("DerivClient.connect() must be called before request()")

        rid = next(self._req_id)
        message = {**payload, "req_id": rid}
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut

        await self._ws.send(json.dumps(message))
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(rid, None)

        if "error" in msg:
            err = msg["error"]
            raise DerivApiError(err.get("message", "Unknown Deriv API error"), code=err.get("code"))
        return msg

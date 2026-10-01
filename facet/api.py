"""REST, WebSocket and dashboard routes for the lifespan-owned Hub."""

from __future__ import annotations

import asyncio
import time
import tomllib
from importlib import metadata
from pathlib import Path

import anyio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api_v2 import register_v2_routes

STATIC = Path(__file__).parent / "static"


def package_version() -> str:
    try:
        return metadata.version("facet")
    except metadata.PackageNotFoundError:
        with (config.ROOT / "pyproject.toml").open("rb") as source:
            return tomllib.load(source)["project"]["version"]


def register_routes(app: FastAPI, dist: Path | None = None) -> None:
    register_v2_routes(app)
    dist = dist if dist is not None else config.ROOT / "web" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "judge": app.state.hub.judge.status, "version": package_version()}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(dist / "index.html" if (dist / "index.html").is_file() else STATIC / "index.html")

    @app.get("/api/state")
    def state() -> JSONResponse:
        hub = app.state.hub
        return JSONResponse({**hub.live(), "latest": hub.latest})

    @app.get("/api/timeline")
    def timeline(date: str | None = None, bucket: int = 5) -> JSONResponse:
        hub = app.state.hub
        return JSONResponse(hub.store.timeline(date, bucket))

    @app.get("/api/summary")
    def summary(date: str | None = None) -> JSONResponse:
        hub = app.state.hub
        return JSONResponse(hub.store.summary(date))

    @app.get("/api/speech")
    def speech(minutes: int = 60) -> JSONResponse:
        hub = app.state.hub
        return JSONResponse(hub.store.recent_speech(minutes * 60))

    @app.post("/api/calibrate")
    def calibrate(seconds: int = 30) -> JSONResponse:
        hub = app.state.hub
        hub.calibrating_until = time.time() + seconds

        def finish() -> None:
            if hub.stopped.wait(seconds + config.FACE_WINDOW_SECONDS + 1):
                return
            hub.store.refresh_baseline()
            hub.apply_baseline()
            hub.store.add_event("calibration", {"seconds": seconds})
            hub.push({"type": "calibrated", "data": hub.status()})

        hub.start_background(finish, "calibration")
        return JSONResponse(hub.status())

    @app.post("/api/pause")
    def pause() -> JSONResponse:
        hub = app.state.hub
        hub.paused = True
        hub.face.paused.set()
        hub.judge.paused.set()
        hub.voice.paused.set()
        hub.hands.paused.set()
        hub.narrator.paused.set()
        hub.wellness.update(False, False, 0, paused=True)
        return JSONResponse(hub.status())

    @app.post("/api/resume")
    def resume() -> JSONResponse:
        hub = app.state.hub
        hub.paused = False
        hub.face.paused.clear()
        hub.judge.paused.clear()
        hub.hands.paused.clear()
        hub.narrator.paused.clear()
        if hub.settings["mic"]:
            hub.voice.paused.clear()
        return JSONResponse(hub.status())

    @app.post("/api/settings")
    async def settings(body: dict) -> JSONResponse:
        hub = app.state.hub
        for key in ("notifications", "mic", "store_transcripts"):
            if key in body:
                hub.settings[key] = bool(body[key])
                hub.store.set_setting(key, bool(body[key]))
        if hub.settings["mic"] and not hub.paused:
            hub.voice.paused.clear()
        else:
            hub.voice.paused.set()
        return JSONResponse(hub.status())

    @app.get("/video.mjpg")
    async def video() -> StreamingResponse:
        hub = app.state.hub
        async def frames():
            hub.face.preview_clients += 1
            last = None
            try:
                while True:
                    jpeg = hub.face.preview_jpeg
                    if jpeg and jpeg is not last:
                        last = jpeg
                        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                    await asyncio.sleep(1 / 15)
            finally:
                hub.face.preview_clients -= 1

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        hub = app.state.hub
        await socket.accept()
        is_app = socket.query_params.get("client") == "app"
        with hub.lock:
            if is_app:
                hub.app_clients += 1
            last = hub.seq

        async def receive_disconnect() -> None:
            try:
                while True:
                    if (await socket.receive())["type"] == "websocket.disconnect":
                        return
            except WebSocketDisconnect:
                pass
            finally:
                group.cancel_scope.cancel()

        async def send_updates() -> None:
            nonlocal last
            try:
                await socket.send_json({"type": "hello", "latest": hub.latest, "status": hub.status()})
                while not hub.stopped.is_set():
                    await socket.send_json(hub.live())
                    with hub.lock:
                        fresh = [e for s, e in hub.events if s > last]
                        last = hub.seq
                    for event in fresh:
                        await socket.send_json(event)
                    await asyncio.sleep(0.2)
            except (WebSocketDisconnect, OSError):
                pass
            finally:
                group.cancel_scope.cancel()

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(receive_disconnect)
                group.start_soon(send_updates)
        finally:
            with hub.lock:
                if is_app:
                    hub.app_clients -= 1

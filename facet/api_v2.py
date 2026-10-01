"""Additive v2 REST routes; model work runs in a request thread, never the event loop."""

from datetime import datetime

from fastapi import Body, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field


class FocusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    minutes: float = Field(default=25, gt=0, le=1440, strict=True)


def checked_date(date):
    if date is not None:
        try:
            parsed = datetime.strptime(date, "%Y-%m-%d")
            if parsed.strftime("%Y-%m-%d") != date:
                raise ValueError
        except ValueError:
            raise HTTPException(422, "date must be YYYY-MM-DD and a valid calendar day") from None
    return date


def register_v2_routes(app: FastAPI):
    @app.get("/api/marks")
    def marks(date: str | None = None):
        return app.state.hub.store.marks(checked_date(date))

    @app.get("/api/captions")
    def captions(minutes: int = Query(default=60, ge=0)):
        return app.state.hub.store.recent_captions(minutes * 60)

    @app.post("/api/focus")
    def focus(body: FocusRequest = Body(default=FocusRequest())):
        return app.state.hub.focus.toggle(body.minutes)

    @app.get("/api/recap")
    def recap(date: str | None = None):
        return app.state.hub.store.cached_recap(checked_date(date))

    @app.post("/api/recap")
    def generate_recap(date: str | None = None):
        date = checked_date(date)
        try:
            return app.state.hub.generate_recap(date)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from None

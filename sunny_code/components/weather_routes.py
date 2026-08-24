"""Routes backing the console's LOCATION card — read/write the location
weather uses. See sunny_code.components.location_store.
"""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from sunny_code.components import location_store, weather


class LocationBody(BaseModel):
    location: str


def create_weather_router() -> APIRouter:
    router = APIRouter(prefix="/api/weather")

    @router.get("/location")
    async def get_location():
        return {"location": location_store.get_location()}

    @router.post("/location")
    async def set_location(body: LocationBody):
        value = body.location.strip()
        if not value:
            return {"status": "error", "message": "Location can't be blank"}
        # Verify against the real OpenWeatherMap API before saving --
        # confirmed live, 2026-08-21: a bad format ("Milton GA" instead of
        # "Milton,GA,US") saved without complaint and 404'd on every
        # weather call for days with nothing telling the user why.
        if not await asyncio.to_thread(weather.location_resolves, value):
            return {
                "status": "error",
                "message": f'"{value}" isn\'t a location OpenWeatherMap recognizes — try "City,State,Country", e.g. "Detroit,MI,US".',
            }
        location_store.set_location(value)
        return {"status": "saved", "location": value}

    return router

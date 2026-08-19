"""Routes backing the console's LOCATION card — read/write the location
weather uses. See sunny_code.components.location_store.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from sunny_code.components import location_store


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
        location_store.set_location(value)
        return {"status": "saved", "location": value}

    return router

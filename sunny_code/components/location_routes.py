"""Receives GPS location reports from OwnTracks (owntracks.org), a free,
open-source phone app that pushes its own periodic location fixes to a
self-hosted HTTP endpoint — no third-party cloud, no subscription. See
sunny_code.components.location_store for where the fix is stored and how
weather.py (and future consumers) read it back.

Payload/response shapes verified against OwnTracks' actual docs
(owntracks.org/booklet/tech/http/, .../tech/json/), not assumed:
- Location messages have _type == "location", with lat/lon/tst required.
- OwnTracks also posts other _type values (transition, card, cmd) to the
  same endpoint — those are accepted and ignored, never treated as errors.
- The server must respond 200 with an empty JSON array ([]), not just any
  2xx — that specific shape is what the OwnTracks client expects back.
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from sunny_code.components import location_store
from sunny_code.config import get_settings, looks_configured

logger = logging.getLogger(__name__)

# auto_error=False: a missing Authorization header shouldn't itself raise —
# whether auth is required at all depends on whether owntracks_shared_secret
# is configured, decided inside the route.
_security = HTTPBasic(auto_error=False)


def create_location_router() -> APIRouter:
    router = APIRouter(prefix="/api/location")

    @router.post("/owntracks")
    async def owntracks_report(request: Request, credentials: HTTPBasicCredentials = Depends(_security)):
        settings = get_settings()
        if looks_configured(settings.owntracks_shared_secret):
            if credentials is None or not secrets.compare_digest(credentials.password, settings.owntracks_shared_secret):
                raise HTTPException(status_code=401, detail="Unauthorized")

        try:
            body = await request.json()
        except ValueError:
            logger.warning("OwnTracks report: unparseable JSON body")
            return []

        if body.get("_type") != "location":
            # transition/card/cmd/etc. — not location data, nothing to do,
            # but still a normal OwnTracks message, not an error.
            return []

        try:
            lat = float(body["lat"])
            lon = float(body["lon"])
        except (KeyError, TypeError, ValueError):
            logger.warning("OwnTracks report: location message missing/invalid lat or lon")
            return []

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            logger.warning(f"OwnTracks report: lat/lon out of range: {lat}, {lon}")
            return []

        location_store.record_gps_fix(lat, lon, tst=body.get("tst"))
        return []

    return router

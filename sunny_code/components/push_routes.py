"""HTTP API for Web Push subscription and sending."""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sunny_code.components import notify, push_service

logger = logging.getLogger(__name__)


class SubscribeRequest(BaseModel):
    subscription: Dict
    label: str = ""


class UnsubscribeRequest(BaseModel):
    endpoint: str


class TestPush(BaseModel):
    title: str = "Sunny"
    body: str = "Push notifications are working."
    url: str = "/sunny"


def create_push_router() -> APIRouter:
    router = APIRouter()

    @router.get("/push/key")
    async def get_public_key():
        """The VAPID public key the browser needs to subscribe.

        Generated on first call if absent. Safe to expose -- it is the
        public half, and a subscription is worthless without the private
        key that stays on this box.
        """
        key = push_service.public_key()
        if key is None:
            return {"available": False, "public_key": None,
                    "detail": "Push libraries are not installed on Sunny."}
        return {"available": True, "public_key": key,
                "subscribers": push_service.subscription_count()}

    @router.post("/push/subscribe")
    async def subscribe(body: SubscribeRequest):
        if not push_service.add_subscription(body.subscription, body.label):
            raise HTTPException(status_code=400, detail="Malformed subscription")
        return {"ok": True, "subscribers": push_service.subscription_count()}

    @router.post("/push/unsubscribe")
    async def unsubscribe(body: UnsubscribeRequest):
        push_service.remove_subscription(body.endpoint)
        return {"ok": True, "subscribers": push_service.subscription_count()}

    @router.get("/push/status")
    async def status():
        return {
            "configured": push_service.is_configured(),
            "subscribers": push_service.subscription_count(),
            "channels": notify.registered(),
        }

    @router.post("/push/test")
    async def test(body: TestPush):
        """Send a test notification to every subscribed device -- the only
        way to confirm the whole chain (keys, subscription, OS delivery)
        actually works, short of waiting for a real reminder."""
        return await notify.send(title=body.title, body=body.body, url=body.url, tag="test")

    return router

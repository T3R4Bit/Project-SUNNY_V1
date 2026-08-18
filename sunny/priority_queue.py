"""Priority queue system for managing concurrent requests across input surfaces."""

import asyncio
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Any


class InputSurface(Enum):
    """Input surfaces that can request Sunny's attention."""
    CLOCK = "clock"           # Bedside device (highest priority when active)
    PHONE = "phone"           # Twilio incoming call
    DISCORD = "discord"       # Discord bot chat
    SCHEDULED = "scheduled"   # Background jobs (lowest priority)


class Priority(Enum):
    """Request priority levels."""
    FOREGROUND = 1  # User actively interacting
    BACKGROUND = 2  # Scheduled or background work

    def __lt__(self, other):
        return self.value < other.value


@dataclass
class Request:
    """A single request for Sunny's attention."""
    id: str
    surface: InputSurface
    priority: Priority
    handler: Callable
    args: tuple = ()
    kwargs: dict = None

    def __lt__(self, other):
        """Sort by priority (lower value = higher priority)."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.id < other.id


class PriorityQueue:
    """
    Priority queue for managing concurrent requests.

    Foreground requests (phone, active clock use) preempt background tasks.
    """

    def __init__(self, max_workers: int = 4):
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.max_workers = max_workers
        self.active_requests = {}
        self.running = False

    async def add(
        self,
        request_id: str,
        surface: InputSurface,
        handler: Callable,
        priority: Priority = Priority.BACKGROUND,
        args: tuple = (),
        kwargs: dict = None,
    ) -> str:
        """
        Add a request to the queue.

        Args:
            request_id: Unique ID for this request
            surface: Which input surface this came from
            handler: Async function to call
            priority: Foreground (user active) or Background
            args: Positional arguments for handler
            kwargs: Keyword arguments for handler

        Returns:
            Request ID
        """
        if kwargs is None:
            kwargs = {}

        req = Request(
            id=request_id,
            surface=surface,
            priority=priority,
            handler=handler,
            args=args,
            kwargs=kwargs,
        )

        await self.queue.put((priority.value, request_id, req))
        return request_id

    async def process(self):
        """Start processing requests (runs until stopped)."""
        self.running = True
        workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.max_workers)
        ]
        await asyncio.gather(*workers)

    async def _worker(self, worker_id: int):
        """Worker coroutine that processes requests."""
        from .logging import logger

        while self.running:
            try:
                _, request_id, req = await asyncio.wait_for(
                    self.queue.get(), timeout=1.0
                )

                logger.info(
                    f"Worker {worker_id} processing {req.surface.value} "
                    f"request {request_id} (priority={req.priority.name})"
                )

                self.active_requests[request_id] = {
                    "surface": req.surface,
                    "status": "running",
                    "worker": worker_id,
                }

                # Execute handler
                try:
                    result = await req.handler(*req.args, **req.kwargs)
                    self.active_requests[request_id]["status"] = "completed"
                    logger.info(f"Request {request_id} completed")
                except Exception as e:
                    self.active_requests[request_id]["status"] = "failed"
                    logger.error(f"Request {request_id} failed: {e}")

                self.queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def stop(self):
        """Stop processing."""
        self.running = False

    def get_status(self) -> dict:
        """Get current queue status."""
        return {
            "queue_size": self.queue.qsize(),
            "active_requests": len(self.active_requests),
            "requests": self.active_requests,
        }

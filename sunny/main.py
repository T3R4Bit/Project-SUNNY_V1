"""Main entry point for Project SUNNY."""

import asyncio
from .logging import logger
from .config import Config, check_config
from .dashboard import init_db, app
from .priority_queue import PriorityQueue


async def main():
    """Start Sunny and all background services."""
    logger.info("=" * 60)
    logger.info("Project SUNNY starting up")
    logger.info("=" * 60)

    # Check configuration
    check_config()

    # Initialize database
    init_db()

    # Initialize priority queue
    queue = PriorityQueue(max_workers=4)
    logger.info("Priority queue initialized (4 workers)")

    # Start dashboard (FastAPI)
    # In production, this runs under uvicorn via systemd
    logger.info(f"Dashboard will be available at http://{Config.TAILSCALE_IP}:{Config.TAILSCALE_PORT}")

    # Start queue processor
    logger.info("Starting request processor...")
    try:
        await queue.process()
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down gracefully...")
        queue.stop()


if __name__ == "__main__":
    asyncio.run(main())

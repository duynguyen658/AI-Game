from __future__ import annotations

import asyncio
import os
import signal
import socket

import structlog

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.database.session import AsyncSessionLocal, dispose_database_engine
from app.jobs.handlers import build_job_handlers
from app.jobs.worker import JobWorker

logger = structlog.get_logger()


async def serve() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    worker = JobWorker(
        worker_id,
        build_job_handlers(AsyncSessionLocal, settings=settings),
        settings=settings,
    )
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, worker.request_stop)
        except NotImplementedError:
            signal.signal(signal_name, lambda *_: worker.request_stop())
    logger.info("worker_started", worker_id=worker_id)
    try:
        await worker.run_forever()
    finally:
        await dispose_database_engine()
        logger.info("worker_stopped", worker_id=worker_id)


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()

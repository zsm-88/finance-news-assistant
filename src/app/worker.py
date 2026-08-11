import asyncio

from app.config import get_settings
from app.db.session import Infrastructure
from app.logging import configure_logging
from app.runtime import run_cycle


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    infrastructure = Infrastructure(settings)
    try:
        while True:
            try:
                async with infrastructure.session_factory() as session:
                    await run_cycle(session, infrastructure.redis, settings)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("worker cycle failed")
            await asyncio.sleep(settings.collect_interval_seconds)
    finally:
        await infrastructure.close()


if __name__ == "__main__":
    asyncio.run(run())

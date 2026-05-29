"""
SevaForge — CLI Entry Point
Run with: python -m sevaforge
"""

import logging
import sys

import uvicorn

from sevaforge.config import get_settings


def main():
    """Start the SevaForge API server."""
    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger("sevaforge")
    logger.info(
        "Starting %s v%s on %s:%d [env=%s]",
        settings.app_name,
        settings.app_version,
        settings.host,
        settings.port,
        settings.environment,
    )

    uvicorn.run(
        "sevaforge.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()

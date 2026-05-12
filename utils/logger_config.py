import logging
import os
from logging.handlers import RotatingFileHandler


def logger_method(name: str) -> logging.Logger:
    """
    Returns a configured logger instance.

    Features:
    - 1 MB rotating file handler in dev
    - Console logging in non-dev
    - Prevents duplicate handlers
    - Windows-safe rotation
    """

    logger = logging.getLogger(name)

    # Prevent log propagation to root logger (avoids duplicate logs)
    logger.propagate = False

    # If handlers already exist, return logger as-is
    if logger.handlers:
        return logger

    # Set base log level
    environment = os.getenv("environment", "prod").lower()
    if environment == "dev":
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if environment == "dev":
        # Windows-safe rotating file handler
        handler = RotatingFileHandler(
            filename="logger.log",
            maxBytes=1 * 1024 * 1024,  # 1 MB
            backupCount=5,
            encoding="utf-8",
            delay=True  # important for Windows file locking
        )
        handler.setLevel(logging.DEBUG)
    else:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
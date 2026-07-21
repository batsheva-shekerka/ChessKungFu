from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any, Optional


def setup_logging(logs_dir: str) -> logging.Logger:
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "server.log")

    logger = logging.getLogger("kungfu_server")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger


class ServerLogger:
    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def info(self, message: str, **ctx: Any) -> None:
        self._logger.info(self._format(message, ctx))

    def warning(self, message: str, **ctx: Any) -> None:
        self._logger.warning(self._format(message, ctx))

    def error(
        self,
        message: str,
        *,
        exc: Optional[BaseException] = None,
        **ctx: Any,
    ) -> None:
        self._logger.error(self._format(message, ctx), exc_info=exc)

    @staticmethod
    def _format(message: str, ctx: dict[str, Any]) -> str:
        if not ctx:
            return message
        parts = " ".join(f"{k}={v}" for k, v in ctx.items() if v is not None)
        return f"{message} | {parts}" if parts else message

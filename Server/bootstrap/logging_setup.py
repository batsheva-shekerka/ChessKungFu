from __future__ import annotations

import os

from infrastructure.logging.error_logger import ServerLogger, setup_logging


def create_server_logger(server_root: str) -> ServerLogger:
    logs_dir = os.path.join(server_root, "logs")
    return ServerLogger(setup_logging(logs_dir))

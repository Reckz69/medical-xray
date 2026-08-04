"""Structured logging setup shared by the gateway and worker."""

import logging
import sys

_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers = [handler]

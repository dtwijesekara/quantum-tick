"""Colored console + file logging, extracted from dt_bot_v8.py."""

from __future__ import annotations

import logging
import sys

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


class CleanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, "%H:%M:%S")
        if record.levelno >= logging.ERROR:
            return f"{RED}{ts}  [ERR]  {record.getMessage()}{RESET}"
        if record.levelno >= logging.WARNING:
            return f"{YELLOW}{ts}  [WARN] {record.getMessage()}{RESET}"
        return f"{ts}  {record.getMessage()}"


def setup_logging(name: str, log_file: str, level: str = "INFO") -> logging.Logger:
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    log = logging.getLogger(name)
    if log.handlers:
        return log  # already configured (e.g. re-imported in tests)

    log.setLevel(level)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    console = logging.StreamHandler(sys.stdout)
    try:
        console.stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    console.setFormatter(CleanFormatter())

    log.addHandler(file_handler)
    log.addHandler(console)
    log.propagate = False
    return log

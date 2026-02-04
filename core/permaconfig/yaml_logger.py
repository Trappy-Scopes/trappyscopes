
"""Create a Yaml logger for Experiments."""

import yaml
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

class YAMLStreamFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            #"msg": record.getMessage(), -> because RichHandler sets "message" internally.
        }

        for k, v in record.__dict__.items():
            if k not in logging.LogRecord("",0,"",0,"",(),None).__dict__:
                entry[k] = v

        return "---\n" + yaml.safe_dump(entry, sort_keys=False)
def create_yaml_logger(
    path: str,
    max_mb: int = 5,
    backups: int = 5
):
    root = logging.getLogger()

    target = Path(path).resolve()

    # --- remove existing YAML file handlers for this path ---
    for h in list(root.handlers):
        if isinstance(h, RotatingFileHandler):
            try:
                if Path(h.baseFilename).resolve() == target:
                    root.removeHandler(h)
                    h.close()
            except Exception:
                pass  # defensive: never break logging

    # --- create fresh handler ---
    handler = RotatingFileHandler(
        target,
        maxBytes=max_mb * 1024 * 1024,
        backupCount=backups,
        encoding="utf-8",
    )
    handler.setFormatter(YAMLStreamFormatter())

    root.addHandler(handler)
    return root
def close_yaml_logger(filename, logger):
    target_file = Path(filename).resolve()
    for h in logger.handlers[:]:
        if isinstance(h, logging.FileHandler):
            if Path(getattr(h, "baseFilename", "")).resolve() == target_file:
                logger.removeHandler(h)
                h.close()


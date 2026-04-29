from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def load_yaml_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing config file at '{config_path}'. "
            "Create it from the project template (config/sources.yaml)."
        )

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Config at '{config_path}' must be a YAML mapping/object.")

    return data

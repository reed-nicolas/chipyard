#!/usr/bin/env python3
"""
Setup .chipyard/config.json for data collection.
Creates config if missing, or updates only enable_data_collection if present.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure util.datacoll is importable when run from scripts/
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from util.datacoll.config import get_default_by_group, load_config as load_config_from_file

# Default config values (must match util/datacoll/config.py)
DEFAULT_ARTIFACT_DIR = "/scratch/chipyard-data"
DEFAULT_CONFIG = {
    "enable_data_collection": "off",
    "db_path": f"{DEFAULT_ARTIFACT_DIR}/chipyard.db",
    "artifact_dir": DEFAULT_ARTIFACT_DIR,
    "build_dir": "builds",
    "log_dir": "logs",
}


def load_config(path: Path) -> dict:
    """Load JSON config. Returns empty dict if missing or invalid."""
    return load_config_from_file(path)


def write_config(path: Path, config: dict) -> None:
    """Write config as pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def run_prompt(chipyard_root: Path) -> str:
    """
    Interactive prompt: Yes -> on, No -> off, Enter -> default.
    Returns "on" or "off".
    """
    default = get_default_by_group(chipyard_root)
    default_label = "yes" if default == "on" else "no"
    print(f"Enable Chipyard data collection (yes/no/[default={default_label}])? ", end="", flush=True)
    while True:
        try:
            line = sys.stdin.readline().strip().lower()
        except (EOFError, KeyboardInterrupt):
            return default
        if line == "":
            return default
        if line in ("y", "yes"):
            return "on"
        if line in ("n", "no"):
            return "off"
        print("Please enter yes, no, or press Enter: ", end="", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Setup .chipyard/config.json for data collection")
    ap.add_argument("--chipyard-dir", metavar="DIR", default=".", help="Chipyard repo root (default: current dir)")
    args = ap.parse_args()

    chipyard_root = Path(args.chipyard_dir).resolve()
    config_path = chipyard_root / ".chipyard" / "config.json"

    # Determine value. First, check the DATACOLL environment variable if set.
    env_val = os.environ.get("DATACOLL", "").strip().lower()
    if env_val in ("on", "off"):
        value = env_val
    elif env_val == "default":
        value = get_default_by_group(chipyard_root)
    else:
        # No override; fall back to interactive prompt or group default when stdin
        # is not a tty (e.g. non-interactive shell).
        if not sys.stdin.isatty():
            value = get_default_by_group(chipyard_root)
        else:
            value = run_prompt(chipyard_root)

    # Load existing or use defaults
    existing = load_config(config_path)
    if existing:
        # Only update enable_data_collection; leave other fields unchanged
        config = dict(existing)
        config["enable_data_collection"] = value
    else:
        config = dict(DEFAULT_CONFIG)
        config["enable_data_collection"] = value

    write_config(config_path, config)
    return 0


if __name__ == "__main__":
    sys.exit(main())

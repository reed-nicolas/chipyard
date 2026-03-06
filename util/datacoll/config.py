"""Load and merge .chipyard/config.json with runtime overrides."""

from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
from pathlib import Path
from typing import Any

# UC Berkeley IP ranges used for group determination
BERKELEY_CIDRS = ["128.32.0.0/16", "136.152.0.0/16", "169.229.0.0/16", "192.31.105.0/24", "10.136.128.0/18", "136.152.16.0/20", "136.152.210.0/23"]


def _is_berkeley_ip() -> bool:
    """
    Return True if the machine's primary outbound IP is in a UC Berkeley range.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        return False
    try:
        addr = ipaddress.ip_address(ip)
        for cidr in BERKELEY_CIDRS:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
    except ValueError:
        return False
    return False


def get_default_by_group(chipyard_root: Path) -> str:
    """
    Determine default enable_data_collection based on user's permission group.
    Returns "on" if EITHER: (a) machine IP is in Berkeley ranges, OR
    (b) git user.email ends with berkeley.edu. Otherwise "off".
    """
    if _is_berkeley_ip():
        return "on"
    try:
        result = subprocess.run(["git", "config", "user.email"], cwd=chipyard_root, capture_output=True, text=True, timeout=5)
        email = (result.stdout or "").strip().lower()
        if email.endswith("berkeley.edu"):
            return "on"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "off"


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load config from JSON file. Returns empty dict if file missing or invalid."""
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_default_config(chipyard_root: Path) -> dict[str, Any]:
    """Return default config values. enable_data_collection uses group-based default."""
    artifact_dir = "/scratch/chipyard-data"
    return {
        "enable_data_collection": get_default_by_group(chipyard_root),
        "db_path": str(Path(artifact_dir) / "chipyard.db"),
        "artifact_dir": artifact_dir,
        "build_dir": "builds",
        "log_dir": "logs",
    }


def resolve_config(config_path: str | Path | None, chipyard_root: Path | None = None) -> dict[str, Any]:
    """Merge file config with defaults. Returns merged dict."""
    root = chipyard_root or Path.cwd()
    default_path = root / ".chipyard" / "config.json"

    path = Path(config_path) if config_path else default_path
    loaded = load_config(path)

    defaults = get_default_config(root)
    defaults.update(loaded)
    return defaults

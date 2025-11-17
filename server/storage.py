from pathlib import Path
import datetime
from typing import Tuple
import logging

LOG = logging.getLogger("sensor_server.storage")


def make_data_dir(dir_path: str = "data") -> Path:
    # Make the directory path relative to the repository root (two levels up from this file)
    repo_root = Path(__file__).resolve().parent.parent
    p = (repo_root / dir_path).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def make_unique_filename(prefix: str = "session", ext: str = ".json") -> str:
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    return f"{prefix}_{ts}{ext}"


def save_raw_json_payload(directory: Path, raw_text: str) -> Tuple[bool, str]:
    fname = make_unique_filename()
    target = directory / fname
    try:
        target.write_text(raw_text, encoding="utf-8")
        LOG.info("Saved payload to %s", str(target))
        return True, str(target.name)
    except Exception as exc:
        LOG.exception("Failed to write file %s: %s", str(target), exc)
        return False, str(exc)

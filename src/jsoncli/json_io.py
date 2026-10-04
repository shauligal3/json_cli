"""Small helpers for reading and writing JSON files."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import JsonCliError


def load_json(path: str | os.PathLike[str]) -> Any:
    """Read and parse a JSON file.

    Key order is preserved, so a document is written back in the order it was
    read.

    Args:
        path: The file to read.

    Returns:
        The parsed JSON value.

    Raises:
        JsonCliError: If the file cannot be read or is not valid JSON.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise JsonCliError(f"cannot open file {path}: {exc.strerror}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonCliError(f"bad JSON in {path}: {exc}") from exc


def dumps(node: Any) -> str:
    """Serialize a JSON value with the indentation used for saved files."""
    return json.dumps(node, indent=4, ensure_ascii=False)


def _file_mode(target: Path) -> int:
    """Return the permission bits a saved file should have.

    An existing file keeps its mode; a new file gets the usual ``0o666``
    filtered by the process umask (``mkstemp`` would otherwise create it 0600).
    """
    try:
        return target.stat().st_mode & 0o777
    except OSError:
        umask = os.umask(0)
        os.umask(umask)
        return 0o666 & ~umask


def save_json(path: str | os.PathLike[str], node: Any) -> int:
    """Write a JSON value to a file atomically.

    The data is written to a temporary file in the same directory and then
    moved into place, so a failed write never leaves a truncated file behind.

    Args:
        path: Destination file.
        node: The JSON value to write.

    Returns:
        The number of characters written.

    Raises:
        JsonCliError: If the file cannot be written.
    """
    data = dumps(node) + "\n"
    target = Path(path)
    try:
        fd, tmp_name = tempfile.mkstemp(dir=target.parent or ".", prefix=f".{target.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
            os.chmod(tmp_name, _file_mode(target))
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise JsonCliError(f"failed to save file {path}: {exc.strerror}") from exc
    return len(data)

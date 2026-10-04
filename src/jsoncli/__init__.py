"""jsoncli - an interactive, schema-aware editor for JSON configuration files."""

from __future__ import annotations

from .document import Document
from .errors import JsonCliError
from .pager import Pager
from .schema import Schema
from .shell import Shell

__version__ = "2.0.0"

__all__ = ["Document", "JsonCliError", "Pager", "Schema", "Shell", "__version__"]

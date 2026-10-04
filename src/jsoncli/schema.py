"""The :class:`Schema` class: the grammar of statements a document accepts."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional

from .constants import (
    ARRAY_LIST,
    DICT_LIST,
    RESERVED_SCHEMA_KEYS,
    SCHEMA_PATH_ENV,
    TYPE,
    VALUES,
)
from .errors import JsonCliError
from .json_io import load_json

SchemaNode = dict[str, Any]
"""A node of the schema tree."""

ParsedStatement = tuple[SchemaNode, list[str], Optional[str], Optional[str]]
"""``(schema node, path to the parent, leaf key or None, value or None)``."""


class Schema:
    """A schema tree describing which statements are legal in a document.

    A schema is a JSON object whose keys are the keywords a user can type.
    Each value is either another object (a branch), or a *leaf* - an object
    with a ``"type"`` key. Two special keys describe collections whose keys are
    chosen by the user rather than by the schema::

        {
            "is-schema": 1,
            "hostname": {"type": "string"},
            "interfaces": {
                "array-list": {"values": {"mtu": {"type": "integer"}}}
            },
            "users": {
                "dict-list": {"values": {"role": {"type": "enum",
                                                 "values": ["admin", "viewer"]}}}
            }
        }

    With this schema, ``interfaces eth0 mtu 1500`` and ``users alice role
    admin`` are valid statements: ``eth0`` and ``alice`` are free-form names.

    Attributes:
        root: The parsed schema tree.
        name: The name under which documents reference this schema.
    """

    def __init__(self, root: SchemaNode, name: str) -> None:
        """Wrap an already-parsed schema tree.

        Args:
            root: The parsed schema tree.
            name: The name under which documents reference this schema.
        """
        self.root = root
        self.name = name

    @classmethod
    def from_file(cls, path: str | os.PathLike[str], name: str | None = None) -> Schema:
        """Load a schema from a JSON file.

        Args:
            path: The schema file.
            name: Name stored in documents that use this schema. Defaults to
                ``path``.

        Raises:
            JsonCliError: If the file cannot be read or is not a JSON object.
        """
        root = load_json(path)
        if not isinstance(root, dict):
            raise JsonCliError(f"schema {path} must be a JSON object")
        return cls(root, name if name is not None else str(path))

    @staticmethod
    def resolve(
        name: str,
        base_dir: str | os.PathLike[str] | None = None,
        search_path: str | None = None,
    ) -> Path:
        """Find the file of a schema referenced by a document.

        The lookup order is: ``name`` as given (absolute, or relative to the
        working directory), relative to ``base_dir`` (normally the directory of
        the document), then each directory in ``search_path``.

        Args:
            name: The schema reference stored in the document.
            base_dir: Directory of the referencing document.
            search_path: ``os.pathsep``-separated directories. Defaults to the
                ``JSONCLI_SCHEMA_PATH`` environment variable.

        Returns:
            The path of the first matching file.

        Raises:
            JsonCliError: If no candidate exists.
        """
        reference = Path(name)
        candidates = [reference]
        if not reference.is_absolute():
            if base_dir is not None:
                candidates.append(Path(base_dir) / reference)
            if search_path is None:
                search_path = os.environ.get(SCHEMA_PATH_ENV, "")
            candidates.extend(Path(d) / reference for d in search_path.split(os.pathsep) if d)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        searched = ", ".join(str(c) for c in candidates)
        raise JsonCliError(
            f"cannot find schema {name!r} (searched: {searched}); "
            f"add its directory to the {SCHEMA_PATH_ENV} environment variable"
        )

    @staticmethod
    def step(node: SchemaNode, token: str) -> SchemaNode:
        """Descend one level in the schema.

        Args:
            node: The current schema node.
            token: The next word of a statement.

        Returns:
            The child node for ``token``: a named child if one exists,
            otherwise the element schema of a collection. An empty dict means
            ``token`` is not valid here.
        """
        if not isinstance(node, dict):
            return {}
        child = node.get(token)
        if isinstance(child, dict):
            return child
        for collection in (ARRAY_LIST, DICT_LIST):
            if collection in node:
                element = node[collection].get(VALUES)
                return element if isinstance(element, dict) else {}
        return {}

    def lookup(self, tokens: Iterable[str]) -> SchemaNode:
        """Return the schema node addressed by a path, or ``{}`` if invalid."""
        node = self.root
        for token in tokens:
            node = self.step(node, token)
            if not node:
                return {}
        return node

    def parse(self, tokens: list[str]) -> ParsedStatement | None:
        """Split a statement into its path, leaf key and value.

        The schema decides where the path ends: the first token that reaches
        a leaf node is the key, and everything after it is the value.

        Args:
            tokens: The words of the statement.

        Returns:
            ``(schema_node, path, key, value)``. If the statement stops at a
            branch, ``key`` and ``value`` are ``None`` and ``path`` is the
            whole statement. ``None`` if a token is not valid.
        """
        node = self.root
        for index, token in enumerate(tokens):
            node = self.step(node, token)
            if not node:
                return None
            if self.is_leaf(node):
                value = " ".join(tokens[index + 1 :]) or None
                return node, tokens[:index], token, value
        return node, list(tokens), None, None

    @staticmethod
    def is_leaf(node: SchemaNode) -> bool:
        """Return whether a schema node describes a single value."""
        return TYPE in node

    @staticmethod
    def is_collection(node: SchemaNode) -> bool:
        """Return whether a schema node has user-named children."""
        return ARRAY_LIST in node or DICT_LIST in node

    @staticmethod
    def is_array(node: SchemaNode) -> bool:
        """Return whether a schema node is stored as a JSON list."""
        return ARRAY_LIST in node

    @staticmethod
    def keywords(node: SchemaNode) -> list[str]:
        """Return the fixed keywords that may follow a schema node.

        Reserved keys and keys starting with ``_`` (handy for comments in a
        schema) are omitted.
        """
        return [
            key
            for key, child in node.items()
            if isinstance(child, dict)
            and key not in RESERVED_SCHEMA_KEYS
            and not key.startswith("_")
        ]

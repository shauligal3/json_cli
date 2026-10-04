"""The :class:`Document` class: a JSON configuration edited against a schema."""

from __future__ import annotations

import os
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

from .constants import (
    BOOL_SET_VALUE,
    MULTI,
    NAME_KEY,
    SCHEMA_KEY,
    TYPE,
    TYPE_BOOL,
    TYPE_ENUM,
    TYPE_INTEGER,
    VALUES,
)
from .errors import JsonCliError
from .json_io import load_json, save_json
from .schema import Schema, SchemaNode


class Document:
    """A JSON document plus the operations the shell performs on it.

    Nodes are addressed by *paths*: lists of words such as
    ``["interfaces", "eth0", "mtu"]``. A word selects a key of an object, or
    the element of a list whose ``"name"`` equals the word.

    Every document can be flattened into *statements* - the ``set`` commands
    that would rebuild it - which is how the shell displays, searches and
    diffs documents.

    Attributes:
        root: The JSON object being edited.
        path: The file the document was loaded from or last saved to.
    """

    def __init__(self, root: dict[str, Any] | None = None, path: Path | None = None) -> None:
        """Create a document.

        Args:
            root: The initial JSON object. Defaults to an empty object.
            path: The file associated with the document, if any.
        """
        self.root: dict[str, Any] = root if root is not None else {}
        self.path = path

    # ------------------------------------------------------------------ files

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> Document:
        """Load a document from a JSON file.

        Raises:
            JsonCliError: If the file cannot be read or is not a JSON object.
        """
        root = load_json(path)
        if not isinstance(root, dict):
            raise JsonCliError(f"{path} must contain a JSON object")
        return cls(root, Path(path))

    def save(self, path: str | os.PathLike[str] | None = None) -> int:
        """Save the document and remember the file name for later saves.

        Args:
            path: Destination file. Defaults to :attr:`path`.

        Returns:
            The number of characters written.

        Raises:
            JsonCliError: If there is no file name or the write fails.
        """
        target = Path(path) if path else self.path
        if target is None:
            raise JsonCliError("missing file name for saving")
        size = save_json(target, self.root)
        self.path = target
        return size

    @property
    def schema_name(self) -> str | None:
        """The schema reference stored in the document, if any."""
        name = self.root.get(SCHEMA_KEY)
        return name if isinstance(name, str) else None

    # -------------------------------------------------------------- navigation

    @staticmethod
    def _find_named(elements: list[Any], name: str) -> dict[str, Any] | None:
        """Return the element of a list whose ``"name"`` is ``name``."""
        for element in elements:
            if isinstance(element, dict) and element.get(NAME_KEY) == name:
                return element
        return None

    def read(self, tokens: list[str]) -> Any:
        """Return the node at a path, or ``None`` if it does not exist."""
        node: Any = self.root
        for token in tokens:
            if isinstance(node, list):
                node = self._find_named(node, token)
            elif isinstance(node, dict):
                node = node.get(token)
            else:
                return None
            if node is None:
                return None
        return node

    def ensure_path(self, tokens: list[str], schema: Schema) -> Any:
        """Return the node at a path, creating any missing nodes on the way.

        The schema decides what a missing node looks like: an empty list for
        an ``array-list``, an empty object otherwise.

        Returns:
            The node, or ``None`` if the path is not valid for the schema.
        """
        node: Any = self.root
        schema_node = schema.root
        for token in tokens:
            schema_node = schema.step(schema_node, token)
            if not schema_node:
                return None
            if isinstance(node, list):
                element = self._find_named(node, token)
                if element is None:
                    element = {NAME_KEY: token}
                    node.append(element)
                node = element
            elif isinstance(node, dict):
                if token not in node:
                    node[token] = [] if schema.is_array(schema_node) else {}
                node = node[token]
            else:
                return None
        return node

    @staticmethod
    def children(node: Any) -> list[str]:
        """Return the names of a node's direct children.

        Object keys, list element names, or scalar list values as strings.
        """
        if isinstance(node, dict):
            return [str(key) for key in node]
        if isinstance(node, list):
            return [
                str(item.get(NAME_KEY, "")) if isinstance(item, dict) else str(item)
                for item in node
            ]
        return []

    # -------------------------------------------------------------- statements

    def statements(self, tokens: list[str] | None = None, prefix: str = "set") -> list[str]:
        """Flatten a subtree into the ``set`` statements that rebuild it.

        Args:
            tokens: Path of the subtree. Defaults to the whole document.
            prefix: The command word that starts each statement.

        Returns:
            The statements in document order; empty if the path is missing.
        """
        tokens = tokens or []
        node = self.read(tokens)
        if node is None:
            return []
        head = " ".join([prefix, *tokens])
        return list(self._statements(node, head, top_level=not tokens))

    @classmethod
    def _statements(cls, node: Any, head: str, *, top_level: bool = False) -> Iterator[str]:
        if isinstance(node, list):
            for item in node:
                if not isinstance(item, dict):
                    yield f"{head} {item}"
                elif NAME_KEY in item:
                    item_head = f"{head} {item[NAME_KEY]}"
                    if len(item) == 1:
                        yield item_head
                    else:
                        yield from cls._statements(item, item_head)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key == NAME_KEY or (top_level and key == SCHEMA_KEY):
                    continue
                if isinstance(value, (list, dict)):
                    if value:
                        yield from cls._statements(value, f"{head} {key}")
                    else:
                        yield f"{head} {key}"
                else:
                    yield f"{head} {key} {value}"

    def diff(self, other: Document) -> tuple[list[str], list[str]]:
        """Compare this document with another one, statement by statement.

        Returns:
            ``(removed, added)``: sorted statements present only in ``other``
            and only in this document, respectively.
        """
        mine = set(self.statements())
        theirs = set(other.statements())
        return sorted(theirs - mine), sorted(mine - theirs)

    # ----------------------------------------------------------------- editing

    def set_value(self, tokens: list[str], schema: Schema) -> None:
        """Apply a ``set`` statement.

        A statement that ends at a branch just creates the branch. A statement
        that reaches a leaf stores its value, converted and validated according
        to the leaf type. ``multi`` leaves accumulate distinct values in a list.

        Raises:
            JsonCliError: If the statement or the value is not valid.
        """
        parsed = schema.parse(tokens)
        if parsed is None:
            raise JsonCliError(f"unknown statement: {' '.join(tokens)}")
        leaf, path, key, value = parsed
        node = self.ensure_path(path, schema)
        if node is None:
            raise JsonCliError(f"cannot create path: {' '.join(path)}")
        if key is None:
            return
        if not isinstance(node, dict):
            raise JsonCliError(f"cannot set {key!r} here")
        if leaf[TYPE] == TYPE_BOOL:
            node[key] = BOOL_SET_VALUE
            return
        if value is None:
            raise JsonCliError(f"missing value for {key!r} (type: {leaf[TYPE]})")
        converted = self._convert(leaf, value)
        current = node.get(key)
        if leaf.get(MULTI) and current is not None:
            if isinstance(current, list):
                if converted not in current:
                    current.append(converted)
            elif current != converted:
                node[key] = [current, converted]
        else:
            node[key] = converted

    @staticmethod
    def _convert(leaf: SchemaNode, value: str) -> Any:
        """Convert a typed-in value to the JSON type required by a leaf."""
        leaf_type = leaf[TYPE]
        if leaf_type == TYPE_INTEGER:
            try:
                return int(value)
            except ValueError:
                raise JsonCliError(f"expecting a number, got {value!r}") from None
        if leaf_type == TYPE_ENUM:
            choices = [str(choice) for choice in leaf.get(VALUES, [])]
            if value not in choices:
                raise JsonCliError(f"expecting one of: {', '.join(choices)}")
        return value

    def remove(self, tokens: list[str]) -> Any:
        """Delete the node or value addressed by a statement.

        The last word may name a key, a list element, or - for a leaf - the
        value to delete. Branches left empty by the deletion are pruned too,
        so that no dangling ``set`` statements remain.

        Returns:
            The removed subtree, suitable for the clipboard: ``{key: value}``
            for an object member, the element itself for a named list element,
            or ``None`` when a plain value was deleted.

        Raises:
            JsonCliError: If nothing matches the statement.
        """
        if not tokens:
            raise JsonCliError("nothing to remove")
        *parent_path, key = tokens
        if key == NAME_KEY:
            raise JsonCliError("cannot delete a reserved key")
        statement = " ".join(tokens)
        node = self.read(parent_path)
        removed: Any = None

        if isinstance(node, list):
            if key in node:
                node.remove(key)
            elif _is_int(key) and int(key) in node:
                node.remove(int(key))
            else:
                element = self._find_named(node, key)
                if element is None:
                    raise JsonCliError(f"unknown statement: {statement}")
                node.remove(element)
                removed = element
            prune = not node
        elif isinstance(node, dict):
            if key not in node:
                raise JsonCliError(f"unknown statement: {statement}")
            removed = {key: node.pop(key)}
            prune = _is_empty_branch(node)
        elif node is not None and (node == key or (_is_int(key) and node == int(key))):
            # The statement ends with the current value of a leaf.
            prune = True
        else:
            raise JsonCliError(f"unknown statement: {statement}")

        # Walk up from the parent, deleting every branch the removal emptied.
        level = len(tokens) - 2
        while prune and level >= 0:
            container = self.read(tokens[:level])
            name = tokens[level]
            if isinstance(container, dict):
                container.pop(name, None)
            elif isinstance(container, list):
                element = self._find_named(container, name)
                if element is not None:
                    container.remove(element)
            else:
                break
            prune = _is_empty_branch(container)
            level -= 1
        return removed

    def paste(
        self,
        path: list[str],
        schema: Schema,
        clip: Any,
        *,
        new_key: str | None = None,
        anchor: str | None = None,
        before: bool = False,
    ) -> None:
        """Insert a clipboard subtree under the node at ``path``.

        Args:
            path: Where to paste.
            schema: Used to check that the key is legal at ``path``.
            clip: A subtree returned by :meth:`remove` or :meth:`copy`.
            new_key: Rename the subtree while pasting.
            anchor: For lists, the element to paste next to. Without an
                anchor the subtree goes to the end, or to the start when
                ``before`` is true.
            before: Insert before ``anchor`` rather than after it.

        Raises:
            JsonCliError: If the key is illegal or already present.
        """
        node = self.ensure_path(path, schema)
        schema_node = schema.lookup(path)
        if isinstance(node, dict):
            if not isinstance(clip, dict) or not clip:
                raise JsonCliError("clipboard content cannot be pasted here")
            old_key = next(iter(clip))
            key = new_key or old_key
            self._check_key_allowed(key, schema_node)
            if key in node:
                raise JsonCliError(f"key {key!r} already exists here")
            node[key] = clip[old_key]
        elif isinstance(node, list):
            if not isinstance(clip, dict):
                raise JsonCliError("clipboard content cannot be pasted here")
            name = new_key or str(clip.get(NAME_KEY, ""))
            if name in self.children(node):
                raise JsonCliError(f"key {name!r} already exists here")
            position = 0 if before and not anchor else len(node)
            if anchor:
                for index, element in enumerate(node):
                    if isinstance(element, dict) and element.get(NAME_KEY) == anchor:
                        position = index if before else index + 1
                        break
            clip[NAME_KEY] = name
            node.insert(position, clip)
        else:
            raise JsonCliError("cannot paste here")

    def rename(self, path: list[str], schema: Schema, old: str, new: str) -> None:
        """Rename a child of the node at ``path``.

        Raises:
            JsonCliError: If ``old`` does not exist, ``new`` already exists or
                ``new`` is not a legal key here.
        """
        node = self.ensure_path(path, schema)
        if isinstance(node, list):
            element = self._find_named(node, old)
            if element is None:
                raise JsonCliError(f"unknown key {old!r}")
            if self._find_named(node, new) is not None:
                raise JsonCliError(f"key {new!r} already exists here")
            element[NAME_KEY] = new
        elif isinstance(node, dict):
            if old not in node:
                raise JsonCliError(f"unknown key {old!r}")
            self._check_key_allowed(new, schema.lookup(path))
            if new in node:
                raise JsonCliError(f"key {new!r} already exists here")
            # Rebuild the object so the renamed key keeps its position.
            items = [(new if key == old else key, value) for key, value in node.items()]
            node.clear()
            node.update(items)
        else:
            raise JsonCliError(f"unknown key {old!r}")

    def copy(self, path: list[str], key: str) -> Any:
        """Return a deep copy of a child of the node at ``path``.

        The result has the same shape as the return value of :meth:`remove`.

        Raises:
            JsonCliError: If the child does not exist.
        """
        node = self.read(path)
        if isinstance(node, list):
            element = self._find_named(node, key)
            if element is not None:
                return deepcopy(element)
        elif isinstance(node, dict) and key in node:
            return {key: deepcopy(node[key])}
        raise JsonCliError(f"unknown key {key!r}")

    @staticmethod
    def _check_key_allowed(key: str, schema_node: SchemaNode) -> None:
        if key not in schema_node and not Schema.is_collection(schema_node):
            allowed = ", ".join(Schema.keywords(schema_node)) or "none"
            raise JsonCliError(f"key {key!r} is illegal here; possible keys: {allowed}")


def _is_int(text: str) -> bool:
    """Return whether ``text`` is a (possibly negative) integer literal."""
    try:
        int(text)
    except ValueError:
        return False
    return True


def _is_empty_branch(node: Any) -> bool:
    """Return whether a container holds nothing but, at most, its name."""
    if isinstance(node, dict):
        return not node or (len(node) == 1 and NAME_KEY in node)
    return isinstance(node, list) and not node

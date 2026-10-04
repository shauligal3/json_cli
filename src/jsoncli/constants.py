"""Reserved keywords of the schema language and of instance documents.

A schema is itself a JSON document. Most of its keys are free-form names that
become editable keywords, but the keys defined here carry special meaning.
"""

from __future__ import annotations

from typing import Final

#: Schema key: the node is an ordered list of named elements.
ARRAY_LIST: Final = "array-list"
#: Schema key: the node is a mapping whose keys are chosen by the user.
DICT_LIST: Final = "dict-list"
#: Schema key holding the element schema of a collection, or an enum's choices.
VALUES: Final = "values"
#: Schema key that marks a node as a leaf and names its value type.
TYPE: Final = "type"
#: Schema key: a leaf may hold several values (stored as a JSON list).
MULTI: Final = "multi"
#: Top-level schema key that identifies a file as a schema.
IS_SCHEMA: Final = "is-schema"

#: Leaf types understood by the editor. Any other type is stored as a string.
TYPE_ENUM: Final = "enum"
TYPE_INTEGER: Final = "integer"
TYPE_BOOL: Final = "bool"

#: Value stored for a ``bool`` leaf that has been set (kept for compatibility
#: with documents written by earlier versions of the tool).
BOOL_SET_VALUE: Final = 1

#: Document key holding the name of an ``array-list`` element.
NAME_KEY: Final = "name"
#: Top-level document key that references the schema file.
SCHEMA_KEY: Final = "schema"

#: Schema keys that are never offered as editable keywords.
RESERVED_SCHEMA_KEYS: Final = frozenset({ARRAY_LIST, DICT_LIST, IS_SCHEMA})

#: Environment variable with extra directories to search for schema files.
SCHEMA_PATH_ENV: Final = "JSONCLI_SCHEMA_PATH"

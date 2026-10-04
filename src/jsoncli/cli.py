"""Command-line entry point: ``jsoncli [--init --schema SCHEMA] FILE``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .constants import IS_SCHEMA, SCHEMA_KEY
from .document import Document
from .errors import JsonCliError
from .json_io import save_json
from .schema import Schema
from .shell import Shell


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="jsoncli",
        description=(
            "Interactive, schema-aware editor for JSON configuration files. "
            "FILE is either a document that references its schema, or a schema "
            "file (to start a new, unsaved document)."
        ),
    )
    parser.add_argument("file", type=Path, metavar="FILE", help="JSON document or schema to open")
    parser.add_argument(
        "-s", "--schema", help="schema reference for a new document (used with --init)"
    )
    parser.add_argument(
        "-i",
        "--init",
        action="store_true",
        help="create FILE as an empty document bound to --schema, then exit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def init_document(path: Path, schema: str) -> None:
    """Create a new, empty document that references ``schema``.

    Raises:
        JsonCliError: If ``path`` already exists or cannot be written.
    """
    if path.exists():
        raise JsonCliError(f"{path} already exists; remove it first")
    save_json(path, {SCHEMA_KEY: schema})


def open_session(path: Path) -> tuple[Schema, Document]:
    """Open a file for editing.

    If the file is a document, its ``"schema"`` reference is resolved (see
    :meth:`Schema.resolve`). If the file is itself a schema (it has an
    ``"is-schema"`` key), a new, unnamed document bound to it is returned.

    Raises:
        JsonCliError: If the file, or the schema it references, is invalid.
    """
    document = Document.load(path)
    schema_ref = document.schema_name
    if schema_ref is not None:
        schema_path = Schema.resolve(schema_ref, base_dir=path.parent)
        return Schema.from_file(schema_path, name=schema_ref), document
    if IS_SCHEMA in document.root:
        schema = Schema(document.root, name=str(path))
        return schema, Document({SCHEMA_KEY: schema.name})
    raise JsonCliError(
        f"{path} is neither a schema (no {IS_SCHEMA!r} key) nor a document (no {SCHEMA_KEY!r} key)"
    )


def configure_readline() -> None:
    """Treat ``-`` as part of a word so names like ``array-list`` complete.

    ``readline`` is not available on every platform (e.g. stock Windows);
    the shell still works there, just without line editing.
    """
    try:
        import readline  # noqa: PLC0415 - optional, platform-dependent import
    except ImportError:
        return
    readline.set_completer_delims(readline.get_completer_delims().replace("-", ""))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line tool and return its exit status."""
    args = build_parser().parse_args(argv)
    try:
        if args.init:
            if not args.schema:
                build_parser().error("--init requires --schema")
            init_document(args.file, args.schema)
            print(f"created {args.file}")
            return 0
        schema, document = open_session(args.file)
    except JsonCliError as exc:
        print(f"jsoncli: {exc}", file=sys.stderr)
        return 1

    configure_readline()
    shell = Shell(schema, document)
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print()
        return 130
    return 0

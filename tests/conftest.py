"""Shared fixtures: the example schema and document from ``examples/``."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest

from jsoncli import Document, Pager, Schema, Shell

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def example_dir(tmp_path: Path) -> Path:
    """A writable copy of the examples directory."""
    for name in ("router.schema.json", "router.json"):
        shutil.copy(EXAMPLES / name, tmp_path / name)
    return tmp_path


@pytest.fixture
def schema(example_dir: Path) -> Schema:
    """The example schema."""
    return Schema.from_file(example_dir / "router.schema.json", name="router.schema.json")


@pytest.fixture
def document(example_dir: Path) -> Document:
    """The example document."""
    return Document.load(example_dir / "router.json")


class ShellHarness:
    """A shell wired to in-memory streams, for driving it from tests."""

    def __init__(self, schema: Schema, document: Document) -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.shell = Shell(
            schema, document, stdin=self.stdin, stdout=self.stdout, pager=Pager(self.stdout)
        )

    def run(self, line: str, answer: str | None = None) -> str:
        """Execute one command line and return what it printed."""
        self.stdin.seek(0)
        self.stdin.truncate()
        if answer is not None:
            self.stdin.write(answer + "\n")
            self.stdin.seek(0)
        self.stdout.seek(0)
        self.stdout.truncate()
        self.last_stop = self.shell.onecmd(line)
        return self.stdout.getvalue()

    @property
    def document(self) -> Document:
        return self.shell.document


@pytest.fixture
def harness(schema: Schema, document: Document) -> ShellHarness:
    """A shell editing the example document."""
    return ShellHarness(schema, document)

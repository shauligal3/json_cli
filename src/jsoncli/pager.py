"""The :class:`Pager` class: prints long output through ``less``."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterable
from typing import IO


class Pager:
    """Write text to a stream, paging it when it does not fit the terminal.

    Paging only happens when the stream is an interactive terminal; when the
    output is redirected (scripts, tests, pipes) everything is written as is.

    Attributes:
        stream: Where output goes when it is not paged.
        command: The pager command line, from ``$PAGER`` or ``less``.
    """

    def __init__(self, stream: IO[str] | None = None, command: str | None = None) -> None:
        """Create a pager.

        Args:
            stream: Output stream. Defaults to ``sys.stdout``.
            command: Pager command line. Defaults to ``$PAGER``, then ``less``.
        """
        self.stream = stream if stream is not None else sys.stdout
        self.command = command if command is not None else os.environ.get("PAGER", "less")

    def page_height(self) -> int | None:
        """Return the terminal height, or ``None`` if output is not a terminal."""
        isatty = getattr(self.stream, "isatty", None)
        if not (callable(isatty) and isatty()):
            return None
        return shutil.get_terminal_size().lines

    def show(self, text: str) -> None:
        """Display ``text``, through the pager if it is taller than the screen."""
        if not text:
            return
        height = self.page_height()
        if height is not None and text.count("\n") + 1 > height and self._run_pager(text):
            return
        self.stream.write(text if text.endswith("\n") else text + "\n")

    def show_lines(self, lines: Iterable[str]) -> None:
        """Display a sequence of lines."""
        self.show("\n".join(lines))

    def _run_pager(self, text: str) -> bool:
        """Pipe ``text`` into the pager; return ``False`` if it cannot run."""
        argv = shlex.split(self.command)
        if not argv:
            return False
        try:
            subprocess.run(argv, input=text, text=True, check=False)
        except OSError:
            return False
        return True

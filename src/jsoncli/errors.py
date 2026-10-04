"""Exception types raised by jsoncli."""

from __future__ import annotations


class JsonCliError(Exception):
    """A user-facing error, such as an unknown statement or an unreadable file.

    The shell catches this exception and prints its message instead of a
    traceback, so the message should be short and self-explanatory.
    """

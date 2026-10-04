"""The :class:`Shell` class: the interactive command loop."""

from __future__ import annotations

import cmd
import os
from typing import IO, Any

from .constants import SCHEMA_KEY, TYPE, TYPE_ENUM, VALUES
from .document import Document
from .errors import JsonCliError
from .json_io import dumps
from .pager import Pager
from .schema import Schema

PASTE_POSITIONS = ("before", "after")


class Shell(cmd.Cmd):
    """An interactive, schema-aware editor for a JSON document.

    Commands work on paths of words (``set interfaces eth0 mtu 1500``) and
    complete with Tab using both the schema and the current document. ``cd``
    moves into a subtree so that later commands are relative to it, and
    commands may be abbreviated to any unambiguous prefix (``sh`` -> ``show``).

    Attributes:
        schema: The schema that validates every edit.
        document: The document being edited.
        edit_root: The path ``cd`` has moved into; ``[]`` at the top level.
        clipboard: The subtree most recently removed with ``rm`` or copied
            with ``cp``, waiting to be pasted.
        pager: Displays long output.
    """

    intro = 'Welcome to jsoncli. Type "help" for a list of commands.'

    def __init__(
        self,
        schema: Schema,
        document: Document,
        *,
        stdin: IO[str] | None = None,
        stdout: IO[str] | None = None,
        pager: Pager | None = None,
    ) -> None:
        """Create a shell.

        Args:
            schema: The schema that validates every edit.
            document: The document to edit.
            stdin: Input stream; defaults to the terminal (with line editing).
            stdout: Output stream; defaults to ``sys.stdout``.
            pager: Displays long output; defaults to a pager on ``stdout``.
        """
        super().__init__(stdin=stdin, stdout=stdout)
        if stdin is not None:
            self.use_rawinput = False
        self.schema = schema
        self.document = document
        self.edit_root: list[str] = []
        self.clipboard: Any = None
        self.pager = pager if pager is not None else Pager(self.stdout)
        self._update_prompt()

    # ----------------------------------------------------------------- helpers

    def _print(self, *parts: object) -> None:
        self.stdout.write(" ".join(str(part) for part in parts) + "\n")

    def _ask(self, question: str) -> str | None:
        """Ask a question; return the answer, or ``None`` at end of input."""
        self.stdout.write(question)
        self.stdout.flush()
        if self.use_rawinput:
            try:
                return input()
            except EOFError:
                return None
        line = self.stdin.readline()
        return line.rstrip("\n") if line else None

    def _confirm(self, question: str, *, on_eof: bool) -> bool:
        """Ask a yes/no question that defaults to "no"."""
        answer = self._ask(f"{question} [y/N] ")
        if answer is None:
            self._print()
            return on_eof
        return answer.strip().lower().startswith("y")

    def _tokens(self, arg: str) -> list[str]:
        """Turn command arguments into an absolute path."""
        return [*self.edit_root, *arg.split()]

    def _update_prompt(self) -> None:
        name = self.document.path.name if self.document.path else "json"
        location = f"{' '.join(self.edit_root)}#" if self.edit_root else ""
        self.prompt = f"{name}@{location} "

    def has_unsaved_changes(self) -> bool:
        """Return whether the document differs from its file on disk."""
        if self.document.path is None:
            return bool(self.document.statements())
        try:
            on_disk = Document.load(self.document.path)
        except JsonCliError:
            return True
        removed, added = self.document.diff(on_disk)
        return bool(removed or added)

    def _command_names(self) -> list[str]:
        return sorted(
            name[3:] for name in self.get_names() if name.startswith("do_") and name != "do_EOF"
        )

    def _match_command(self, word: str) -> list[str]:
        names = self._command_names()
        if word in names:
            return [word]
        return [name for name in names if name.startswith(word)]

    # ---------------------------------------------------------- cmd.Cmd hooks

    def emptyline(self) -> bool:
        """Do nothing on an empty line (instead of repeating the last command)."""
        return False

    # typeshed annotates Cmd.default as returning None, but onecmd() passes its
    # result on as the "stop" flag - which an abbreviated "quit" relies on.
    def default(self, line: str) -> bool:  # type: ignore[override]
        """Run a command given by an unambiguous prefix of its name."""
        word, _, rest = line.strip().partition(" ")
        matches = self._match_command(word)
        if len(matches) == 1:
            return bool(getattr(self, f"do_{matches[0]}")(rest))
        if matches:
            self._print(f"ambiguous command {word!r}: {', '.join(matches)}")
        else:
            self._print(f"unknown command: {word} (type 'help' for a list)")
        return False

    def completedefault(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete the arguments of an abbreviated command."""
        words = line.split()
        matches = self._match_command(words[0]) if words else []
        if len(matches) == 1:
            completer = getattr(self, f"complete_{matches[0]}", None)
            if completer is not None:
                result: list[str] = completer(text, line, begidx, endidx)
                return result
        return []

    # ------------------------------------------------------------ completion

    def _complete_tree(self, text: str, line: str, begidx: int, _endidx: int) -> list[str]:
        """Complete a path from schema keywords, enum values and document keys."""
        tokens = self._tokens(" ".join(line[:begidx].split()[1:]))
        schema_node = self.schema.lookup(tokens)
        if not schema_node:
            return []
        if Schema.is_leaf(schema_node):
            if schema_node[TYPE] == TYPE_ENUM:
                choices = [str(choice) for choice in schema_node.get(VALUES, [])]
                return [choice for choice in choices if choice.startswith(text)]
            return []
        options = Schema.keywords(schema_node)
        if Schema.is_collection(schema_node):
            options += Document.children(self.document.read(tokens))
        return [option for option in dict.fromkeys(options) if option.startswith(text)]

    @staticmethod
    def _complete_path(text: str, line: str, _begidx: int, endidx: int) -> list[str]:
        """Complete a file name.

        ``text`` is the part of the word readline will replace; depending on
        the completer delimiters it is the whole path or only its last part.
        """
        typed = line[:endidx]
        word = typed.split()[-1] if typed and not typed[-1].isspace() else ""
        directory, base = os.path.split(word)
        try:
            entries = sorted(os.listdir(directory or "."))
        except OSError:
            return []
        replaced_from = len(word) - len(text)
        results = []
        for entry in entries:
            if entry.startswith(base):
                full = os.path.join(directory, entry)
                suffix = "/" if os.path.isdir(full) else ""
                results.append(full[replaced_from:] + suffix)
        return results

    def _edit_children(self) -> list[str]:
        return Document.children(self.document.read(self.edit_root))

    complete_set = _complete_tree
    complete_rm = _complete_tree
    complete_cd = _complete_tree
    complete_ls = _complete_tree
    complete_json = _complete_tree
    complete_schema = _complete_tree
    complete_show = _complete_tree
    complete_save = _complete_path
    complete_load = _complete_path
    complete_diff = _complete_path

    def complete_paste(self, text: str, line: str, begidx: int, _endidx: int) -> list[str]:
        """Complete ``paste [before|after] [CHILD]``."""
        args = line[:begidx].split()[1:]
        if not args:
            return [word for word in PASTE_POSITIONS if word.startswith(text)]
        if len(args) == 1 and args[0] in PASTE_POSITIONS:
            return [name for name in self._edit_children() if name.startswith(text)]
        return []

    def complete_mv(self, text: str, line: str, begidx: int, _endidx: int) -> list[str]:
        """Complete the first argument of ``mv``/``cp`` with existing children."""
        if line[:begidx].split()[1:]:
            return []
        return [name for name in self._edit_children() if name.startswith(text)]

    complete_cp = complete_mv

    # -------------------------------------------------------------- commands

    def do_set(self, arg: str) -> None:
        """set PATH... [KEY [VALUE]]

        Set a value, creating any missing nodes along the path. The schema
        validates the path and the value (integer, enum, bool, ...).
        Example: set interfaces eth0 mtu 1500
        """
        tokens = self._tokens(arg)
        if not tokens:
            self._print("usage: set PATH... [KEY [VALUE]]")
            return
        try:
            self.document.set_value(tokens, self.schema)
        except JsonCliError as exc:
            self._print(exc)

    def do_rm(self, arg: str) -> None:
        """rm PATH... [VALUE]

        Delete a subtree, element or value. A deleted subtree is kept in the
        clipboard and can be put back with 'paste'.
        """
        if not arg.split():
            self._print("usage: rm PATH... [VALUE]")
            return
        try:
            removed = self.document.remove(self._tokens(arg))
        except JsonCliError as exc:
            self._print(exc)
            return
        if removed is not None:
            self.clipboard = removed

    def do_cd(self, arg: str) -> None:
        """cd [PATH... | .. | /]

        Move into a subtree so later commands are relative to it. 'cd ..'
        goes up one level; 'cd' or 'cd /' returns to the top.
        """
        arg = arg.strip()
        if arg in ("", "/"):
            self.edit_root = []
        elif arg == "..":
            self.edit_root = self.edit_root[:-1]
        else:
            tokens = self._tokens(arg)
            schema_node = self.schema.lookup(tokens)
            if Schema.is_leaf(schema_node):
                self._print(f"cannot cd into leaf {tokens[-1]!r}")
                return
            if self.document.ensure_path(tokens, self.schema) is None:
                self._print(f"unknown path: {' '.join(tokens)}")
                return
            self.edit_root = tokens
        self._update_prompt()

    def do_ls(self, arg: str) -> None:
        """ls [PATH...]

        List the direct children of the current node or of PATH.
        """
        self.pager.show_lines(Document.children(self.document.read(self._tokens(arg))))

    def do_json(self, arg: str) -> None:
        """json [PATH...]

        Print the document, or the subtree at PATH, as JSON.
        """
        node = self.document.read(self._tokens(arg))
        if node is None:
            self._print(f"unknown path: {arg.strip()}")
            return
        self.pager.show(dumps(node))

    def do_schema(self, arg: str) -> None:
        """schema [PATH...]

        Print the schema, or the part of it that applies at PATH.
        """
        node = self.schema.lookup(self._tokens(arg))
        if not node:
            self._print(f"unknown path: {arg.strip()}")
            return
        self.pager.show(dumps(node))

    def do_show(self, arg: str) -> None:
        """show [PATH...]

        Print the document, or the subtree at PATH, as 'set' statements.
        """
        self.pager.show_lines(self.document.statements(self._tokens(arg)))

    def do_grep(self, arg: str) -> None:
        """grep TEXT

        Print the 'set' statements (under the current node) containing TEXT.
        """
        needle = arg.strip()
        statements = self.document.statements(self.edit_root)
        self.pager.show_lines(line for line in statements if needle in line)

    def do_diff(self, arg: str) -> None:
        """diff [FILE]

        Compare the document with FILE (default: the file it was loaded from),
        statement by statement.
        """
        target = arg.strip() or self.document.path
        try:
            other = Document.load(target) if target else Document()
        except JsonCliError as exc:
            self._print(exc)
            return
        removed, added = self.document.diff(other)
        if not removed and not added:
            self._print("no differences")
            return
        lines: list[str] = []
        if removed:
            lines += ["Removed statements:", *removed, ""]
        if added:
            lines += ["Added statements:", *added]
        self.pager.show_lines(lines)

    def do_save(self, arg: str) -> None:
        """save [FILE]

        Save the document to FILE (default: the file it was loaded from).
        """
        try:
            size = self.document.save(arg.strip() or None)
        except JsonCliError as exc:
            self._print(exc)
            return
        self._update_prompt()
        self._print(f"saved {size} bytes to {self.document.path}")

    def do_load(self, arg: str) -> None:
        """load [FILE]

        Replace the document with FILE (default: reload the current file).
        Asks for confirmation if there are unsaved changes.
        """
        target = arg.strip() or self.document.path
        if not target:
            self._print("usage: load FILE")
            return
        if self.has_unsaved_changes() and not self._confirm(
            "Discard unsaved changes?", on_eof=False
        ):
            return
        try:
            document = Document.load(target)
        except JsonCliError as exc:
            self._print(exc)
            return
        document.root[SCHEMA_KEY] = self.schema.name
        self.document = document
        self.edit_root = []
        self._update_prompt()
        self._print(f"loaded {target}")

    def do_clipboard(self, _arg: str) -> None:
        """clipboard

        Print the clipboard content.
        """
        if self.clipboard is None:
            self._print("clipboard is empty")
        else:
            self.pager.show(dumps(self.clipboard))

    def do_paste(self, arg: str) -> None:
        """paste [before|after [CHILD]]

        Insert the clipboard into the current node. In a list, the position
        can be given relative to an existing CHILD; 'paste before' alone puts
        it first. The default is to append.
        """
        if self.clipboard is None:
            self._print("clipboard is empty")
            return
        words = arg.split()
        if len(words) > 2 or (words and words[0] not in PASTE_POSITIONS):
            self._print("usage: paste [before|after [CHILD]]")
            return
        try:
            self.document.paste(
                self.edit_root,
                self.schema,
                self.clipboard,
                anchor=words[1] if len(words) > 1 else None,
                before=bool(words) and words[0] == "before",
            )
        except JsonCliError as exc:
            self._print(exc)
            return
        self.clipboard = None

    def do_mv(self, arg: str) -> None:
        """mv OLD NEW

        Rename a child of the current node.
        """
        words = arg.split()
        if len(words) != 2:
            self._print("usage: mv OLD NEW")
            return
        try:
            self.document.rename(self.edit_root, self.schema, words[0], words[1])
        except JsonCliError as exc:
            self._print(exc)

    def do_cp(self, arg: str) -> None:
        """cp CHILD [NEW]

        Copy a child of the current node to the clipboard, or - with NEW -
        duplicate it right away under the name NEW.
        """
        words = arg.split()
        if len(words) not in (1, 2):
            self._print("usage: cp CHILD [NEW]")
            return
        try:
            self.clipboard = self.document.copy(self.edit_root, words[0])
            if len(words) == 2:
                self.document.paste(self.edit_root, self.schema, self.clipboard, new_key=words[1])
                self.clipboard = None
        except JsonCliError as exc:
            self._print(exc)

    def do_exit(self, _arg: str) -> bool:
        """exit

        Return to the top level, or quit when already there.
        """
        if self.edit_root:
            self.edit_root = []
            self._update_prompt()
            return False
        return self.do_quit("")

    def do_quit(self, _arg: str) -> bool:
        """quit

        Leave the editor. Asks for confirmation if there are unsaved changes.
        """
        if self.has_unsaved_changes():
            return self._confirm("Quit without saving?", on_eof=True)
        return True

    def do_EOF(self, _arg: str) -> bool:  # noqa: N802 - name required by cmd.Cmd
        """Quit on Ctrl-D."""
        self._print()
        return self.do_quit("")

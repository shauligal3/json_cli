# jsoncli

[![CI](https://github.com/shauligal3/json_cli/actions/workflows/ci.yml/badge.svg)](https://github.com/shauligal3/json_cli/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

An interactive, **schema-aware shell for editing JSON configuration files** — in the
spirit of the configuration CLIs found on network devices (Junos, VyOS, EdgeOS).

Instead of hand-editing nested JSON, you type flat statements such as
`set interfaces eth0 mtu 1500`. A small JSON schema drives Tab completion, validates
every edit (integers, enums, flags, multi-valued fields) and decides how the tree is
shaped, so the file on disk is always well-formed.

```text
$ jsoncli examples/router.json
Welcome to jsoncli. Type "help" for a list of commands.
router.json@ show users
set users alice role admin
set users alice shell /bin/bash
set users bob role viewer
router.json@ cd interfaces eth1
router.json@interfaces eth1# set mtu big
expecting a number, got 'big'
router.json@interfaces eth1# set mtu 1400
router.json@interfaces eth1# cd
router.json@ diff
Removed statements:
set interfaces eth1 mtu 9000

Added statements:
set interfaces eth1 mtu 1400
router.json@ save
saved 689 bytes to router.json
```

## Features

- **Flat "set" syntax** for deeply nested JSON, with the document viewable either as JSON
  (`json`) or as the list of statements that rebuild it (`show`).
- **Schema-driven Tab completion** of keywords, enum values and the names already present
  in the document. Commands can be abbreviated to any unambiguous prefix (`sh` → `show`).
- **Validation** of every value against its leaf type before it touches the document.
- **Navigation** with `cd`, so long paths only have to be typed once.
- **Cut / copy / paste / rename** of whole subtrees, including ordered insertion into lists.
- **Statement-level diff** against the saved file (or any other file), and a confirmation
  prompt before discarding unsaved changes.
- **Safe saves**: files are written atomically and keep their permissions.
- No runtime dependencies — only the Python standard library.

## Installation

```bash
git clone https://github.com/shauligal3/json_cli.git
cd json_cli
pip install .          # or: pip install -e ".[dev]" for development
```

This installs a `jsoncli` command (also runnable as `python -m jsoncli`).

## Usage

```bash
jsoncli config.json                              # edit a document
jsoncli my.schema.json                           # start a new document from a schema
jsoncli --init --schema my.schema.json new.json  # create an empty document, then exit
```

A document names its schema in a top-level `"schema"` key. The schema file is looked up
as given, then next to the document, then in each directory listed in the
`JSONCLI_SCHEMA_PATH` environment variable (`:`-separated, `;` on Windows).

### Commands

| Command | Description |
| --- | --- |
| `set PATH... [KEY [VALUE]]` | Set a value, creating missing nodes along the path. |
| `rm PATH... [VALUE]` | Delete a subtree, element or value; empty parents are pruned. The subtree goes to the clipboard. |
| `cd [PATH... \| .. \| /]` | Move into a subtree; later commands are relative to it. |
| `ls [PATH...]` | List the children of a node. |
| `show [PATH...]` | Print a subtree as `set` statements. |
| `json [PATH...]` | Print a subtree as JSON. |
| `grep TEXT` | Print the statements containing `TEXT`. |
| `schema [PATH...]` | Print the schema that applies at a path. |
| `cp CHILD [NEW]` | Copy a child to the clipboard, or duplicate it as `NEW`. |
| `mv OLD NEW` | Rename a child. |
| `paste [before\|after [CHILD]]` | Insert the clipboard into the current node. |
| `clipboard` | Show the clipboard. |
| `diff [FILE]` | Compare with the saved file (or `FILE`), statement by statement. |
| `save [FILE]` / `load [FILE]` | Write or (re)load the document. |
| `exit` / `quit` / Ctrl-D | Leave the current subtree, or quit. |

`help COMMAND` prints the details of any command. Long output is shown through `$PAGER`
(default `less`) when it does not fit the terminal.

## Schema format

A schema is a JSON object marked with `"is-schema"`. Its keys are the keywords a user can
type; each value is either a branch (another object) or a **leaf** (an object with a
`"type"`). Two special keys introduce collections whose member names are chosen by the
user:

```json
{
    "is-schema": 1,
    "hostname": {"type": "string"},
    "logging": {
        "level": {"type": "enum", "values": ["debug", "info", "warning", "error"]},
        "remote-host": {"type": "string", "multi": 1},
        "verbose": {"type": "bool"}
    },
    "interfaces": {
        "array-list": {"values": {"mtu": {"type": "integer"}}}
    },
    "users": {
        "dict-list": {"values": {"role": {"type": "enum", "values": ["admin", "viewer"]}}}
    }
}
```

| Construct | Meaning | Stored as |
| --- | --- | --- |
| `{"type": "string"}` | Free text (any unknown type is also treated as text). | `"value"` |
| `{"type": "integer"}` | Whole number, validated on input. | `1500` |
| `{"type": "enum", "values": [...]}` | One of a fixed set; completes with Tab. | `"info"` |
| `{"type": "bool"}` | A flag: `set logging verbose` turns it on, `rm` turns it off. | `1` |
| `"multi": 1` on a leaf | Repeated `set`s accumulate distinct values. | `["a", "b"]` |
| `"array-list"` | Ordered list of named elements (`interfaces eth0 ...`). | `[{"name": "eth0", ...}]` |
| `"dict-list"` | Object with user-chosen keys (`users alice ...`). | `{"alice": {...}}` |

Keys starting with `_` are ignored, which makes them handy for comments. See
[`examples/`](examples) for a complete schema and a matching document.

## Project layout

```text
src/jsoncli/
├── cli.py         # argument parsing, opening a document or schema, entry point
├── shell.py       # Shell     - the interactive cmd.Cmd loop, completion, commands
├── document.py    # Document  - the JSON tree: navigation, statements, edit operations
├── schema.py      # Schema    - schema lookup, statement parsing, schema file resolution
├── pager.py       # Pager     - terminal-aware output paging
├── json_io.py     # loading and atomic saving of JSON files
├── errors.py      # JsonCliError, the user-facing error type
└── constants.py   # reserved keywords of the schema language
```

The editing logic lives in `Document` and `Schema`, which know nothing about terminals;
`Shell` only parses command lines, reports errors and handles completion. This keeps the
core fully unit-testable and lets the shell be driven by in-memory streams in the tests.

## Development

```bash
pip install -e ".[dev]"
pytest --cov          # tests
ruff check .          # lint
ruff format .         # format
mypy                  # strict type checking
```

CI runs all of the above on Python 3.9 – 3.13 for every push and pull request.

## License

Released under the [MIT License](LICENSE).

#!/usr/bin/env vpython3
# [VPYTHON:BEGIN]
# python_version: "3.11"
# # Note: mdformat depends on mdurl and markdown-it-py, which are included above.
# wheel: <
#   name: "infra/python/wheels/mdurl-py3"
#   version: "version:0.1.2"
# >
# wheel: <
#   name: "infra/python/wheels/markdown-it-py-py3"
#   version: "version:2.2.0"
# >
# wheel: <
#   name: "infra/python/wheels/mdformat-py3"
#   version: "version:0.7.22"
# >
# wheel: <
#   name: "infra/python/wheels/mdit-py-plugins-py3"
#   version: "version:0.5.0"
# >
# wheel: <
#   name: "infra/python/wheels/mdformat_frontmatter-py3"
#   version: "version:2.0.10"
# >
# wheel: <
#   name: "infra/python/wheels/ruamel_yaml-py3"
#   version: "version:0.17.16"
# >
# [VPYTHON:END]

# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Markdown formatting wrapper for depot_tools."""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from typing import Iterable, Optional

import mdformat
import setup_color
import utils
from third_party import colorama

# Internal formatting rules.
_WRAP_WIDTH = '80'
_CONFIG_FILENAME = '.style.mdformat'


def _get_colored_diff(diff: Iterable[str]) -> str:
    """Adds ANSI colors to a unified diff if the output is a TTY."""
    if not setup_color.IS_TTY:
        return ''.join(diff)

    colored_lines = []
    for line in diff:
        if line.startswith('---') or line.startswith('+++'):
            colored_lines.append(line)
        elif line.startswith('-'):
            colored_lines.append(colorama.Fore.RED + line +
                                 colorama.Style.RESET_ALL)
        elif line.startswith('+'):
            colored_lines.append(colorama.Fore.GREEN + line +
                                 colorama.Style.RESET_ALL)
        elif line.startswith('@@'):
            colored_lines.append(colorama.Fore.CYAN + line +
                                 colorama.Style.RESET_ALL)
        else:
            colored_lines.append(line)
    return ''.join(colored_lines)


def print_diff(original: str, formatted: str, filename: str) -> int:
    """Prints a unified diff between original and formatted text.

    Returns:
        2 if differences were found, 0 otherwise.
    """
    diff = list(
        difflib.unified_diff(original.splitlines(keepends=True),
                             formatted.splitlines(keepends=True),
                             fromfile=f'a/{filename}',
                             tofile=f'b/{filename}'))

    if not diff:
        return 0

    sys.stdout.write(_get_colored_diff(diff))
    return 2


def process_stdin(args: argparse.Namespace) -> int:
    """Handles formatting when input is provided via stdin.

    This mode is primarily used for integration with tools like `jj fix`,
    which operates on a "pipe model": it streams file content to the
    formatter's stdin and expects the formatted result on stdout.
    `jj fix` handles stacked commits by iterating over each revision in the
    stack and applying the formatter to the changed files. See the "Execution
    Example" in `jj help fix` for more details.

    Since `jj fix` does not provide the original file path as a positional
    argument when piping, we use `--assume-filename` to pass the path
    separately. This allows us to perform the recursive opt-in check
    (searching for `.style.mdformat`) based on the file's location in the
    directory hierarchy.
    """
    if args.files:
        print('Error: Cannot specify files with --from-stdin.', file=sys.stderr)
        return 1

    original = sys.stdin.read()

    # Opt-in check for stdin if a filename hint is provided.
    if args.assume_filename:
        if not utils.find_config_file(args.assume_filename, _CONFIG_FILENAME):
            # Not opted-in. Stream original input to stdout for pipes and exit.
            if not args.check and not args.diff:
                sys.stdout.write(original)
            return 0

    try:
        formatted = mdformat.text(original,
                                  options={
                                      'wrap': int(_WRAP_WIDTH),
                                      'number': True
                                  },
                                  extensions={'frontmatter'})
    except Exception as e:
        sys.stderr.write(f'Error formatting: {e}\n')
        return 1

    if args.diff:
        return print_diff(original, formatted, args.assume_filename or 'stdin')

    if args.check:
        if original != formatted:
            print('Markdown content is not formatted.', file=sys.stderr)
            return 2
        return 0

    # Default filter mode: Output formatted content for pipes.
    sys.stdout.write(formatted)
    return 0


def process_files(args: argparse.Namespace) -> int:
    """Handles formatting for a list of files on disk."""
    return_value = 0
    for path in args.files:
        if not os.path.exists(path):
            print(f'Error: File not found: {path}', file=sys.stderr)
            return_value = 1
            continue

        # Opt-in check: only format if a marker file is found.
        if not utils.find_config_file(path, _CONFIG_FILENAME):
            continue

        with open(path, 'r', encoding='utf-8') as f:
            original = f.read()

        try:
            formatted = mdformat.text(original,
                                      options={
                                          'wrap': int(_WRAP_WIDTH),
                                          'number': True
                                      },
                                      extensions={'frontmatter'})
        except Exception as e:
            print(f'Error formatting {path}: {e}', file=sys.stderr)
            return_value = 1
            continue

        if args.diff:
            ret = print_diff(original, formatted, path)
            return_value = return_value or ret
        elif args.check:
            if original != formatted:
                print(f'File "{path}" is not formatted.', file=sys.stderr)
                return_value = return_value or 2
        else:
            if original != formatted:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(formatted)
                print(f'Formatted {path}')

    if return_value == 2 and args.check:
        print('\nMarkdown files are not formatted correctly.', file=sys.stderr)
        print('To fix, run:', file=sys.stderr)
        print(f'  git cl format {" ".join(args.files)}', file=sys.stderr)

    return return_value


def main() -> int:
    setup_color.init()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--check',
        action='store_true',
        help='Check formatting and return non-zero if not formatted.')
    parser.add_argument(
        '--diff',
        action='store_true',
        help='Print diff to stdout rather than modifying files.')
    parser.add_argument('--from-stdin',
                        action='store_true',
                        help='Read from stdin.')
    parser.add_argument('--assume-filename',
                        help='Filename hint when using --from-stdin.')
    parser.add_argument('files', nargs='*', help='Markdown files to process.')
    args = parser.parse_args()

    if args.from_stdin:
        return process_stdin(args)

    if not args.files:
        return 0

    return process_files(args)


if __name__ == '__main__':
    sys.exit(main())

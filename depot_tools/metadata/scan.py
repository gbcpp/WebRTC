#!/usr/bin/env python3
# Copyright 2023 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
from collections import defaultdict
import json
import os
import sys

_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
# The repo's root directory.
_ROOT_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))

# Add the repo's root directory for clearer imports.
sys.path.insert(0, _ROOT_DIR)

import metadata.discover
import metadata.validate


def parse_args() -> argparse.Namespace:
    """Helper to parse args to this script."""
    parser = argparse.ArgumentParser()
    repo_root_dir = parser.add_argument(
        "repo_root_dir",
        help=("The path to the repository's root directory, which will be "
              "scanned for Chromium metadata files, e.g. '~/chromium/src'."),
    )
    parser.add_argument(
        "--is-open-source-project",
        action="store_true",
        help="Whether the project is open source (allows reciprocal licenses).",
    )
    parser.add_argument(
        "--json-summary",
        help="Path to save the validation summary in JSON format.",
    )

    args = parser.parse_args()

    # Check the repo root directory exists.
    src_dir = os.path.abspath(args.repo_root_dir)
    if not os.path.exists(src_dir) or not os.path.isdir(src_dir):
        raise argparse.ArgumentError(
            repo_root_dir,
            f"Invalid repository root directory '{src_dir}' - not found",
        )

    return args


def main() -> None:
    """Runs validation on all metadata files within the directory
    specified by the repo_root_dir arg.
    """
    config = parse_args()
    src_dir = os.path.abspath(config.repo_root_dir)

    metadata_files = metadata.discover.find_metadata_files(src_dir)
    file_count = len(metadata_files)
    if not config.json_summary:
        print(f"Found {file_count} metadata files.")

    invalid_file_count = 0

    # Data structure for JSON output
    json_output = {
        "files": {},
        "summary": {
            "total_files": file_count,
            "invalid_files": 0,
        }
    }

    # Key is constructed from the result severity and reason;
    # Value is a dict for:
    #  * list of files affected by that reason at that severity; and
    #  * list of validation result strings for that reason and severity.
    all_reasons = defaultdict(lambda: {"files": [], "results": set()})
    for filepath in metadata_files:
        file_results = metadata.validate.validate_file(
            filepath,
            repo_root_dir=src_dir,
            is_open_source_project=config.is_open_source_project)
        invalid = False
        relpath = os.path.relpath(filepath, start=src_dir)

        if file_results:
            json_output["files"][relpath] = []

            if not config.json_summary:
                print(f"\n{len(file_results)} problem(s) in {relpath}:")

            for result in file_results:
                if not config.json_summary:
                    print(f"    {result}")

                # Add to JSON structure
                json_output["files"][relpath].append({
                    "severity":
                    result.get_severity_prefix(),
                    "reason":
                    result.get_reason(),
                    "message":
                    str(result),
                    "fatal":
                    result.is_fatal(),
                })

                summary_key = "{severity} - {reason}".format(
                    severity=result.get_severity_prefix(),
                    reason=result.get_reason())
                all_reasons[summary_key]["files"].append(relpath)
                all_reasons[summary_key]["results"].add(str(result))
                if result.is_fatal():
                    invalid = True

        if invalid:
            invalid_file_count += 1

    json_output["summary"]["invalid_files"] = invalid_file_count

    if config.json_summary:
        with open(config.json_summary, 'w') as f:
            json.dump(json_output, f, indent=2)
        return

    print("\n\nDone.")

    print("\nSummary of files:")
    for summary_key, data in all_reasons.items():
        affected_files = data["files"]
        count = len(affected_files)
        plural = "s" if count > 1 else ""
        print(f"\n  {count} file{plural}: {summary_key}")
        for affected_file in affected_files:
            print(f"    {affected_file}")

    print("\nSummary of results:")
    for summary_key, data in all_reasons.items():
        results = data["results"]
        count = len(results)
        plural = "s" if count > 1 else ""
        print(f"\n  {count} issue{plural}: {summary_key}")
        for result in sorted(results):
            print(f"    {result}")

    print(f"\n\n{invalid_file_count} / {file_count} metadata files are "
          "invalid, i.e. the file has at least one fatal validation issue.")


if __name__ == "__main__":
    main()

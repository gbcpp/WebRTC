#!/usr/bin/env vpython3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# [VPYTHON:BEGIN]
# python_version: "3.11"
# wheel: <
#   name: "infra/python/wheels/protobuf-py3"
#   version: "version:4.25.1"
# >
# wheel: <
#   name: "infra/python/wheels/googleapis-common-protos-py2_py3"
#   version: "version:1.61.0"
# >
# [VPYTHON:END]

import json
import os
import sys

_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
_METADATA_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
sys.path.insert(0, _METADATA_DIR)

import restrictive_license_approval_pb2 as rla_pb2
from google.protobuf import text_format

def main():
    if len(sys.argv) != 2:
        print("Usage: parse_restrictive_license_approval.py <path_to_textproto>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    proto_msg = rla_pb2.RestrictiveLicenseApproval()
    try:
        with open(path, "r", encoding="utf-8") as f:
            text_format.Parse(f.read(), proto_msg)
    except Exception as e:
        print(f"Error parsing proto: {e}", file=sys.stderr)
        sys.exit(2)

    approvals = []
    for approval in proto_msg.license_approval:
        # Approval requires a License ID and bug.
        if approval.id and approval.bug:
            approvals.append({
                "id": approval.id,
                "bug": approval.bug,
            })

    print(json.dumps(approvals))

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# Copyright 2024 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# These licenses are used to verify that code imported to Android complies with
# their licensing requirements. Do not add entries to this list without approval.
# SPDX Identifiers are preferred when available. For the full list of
# identifiers; see https://spdx.org/licenses/.
# Licenses are grouped by their classification (restrictiveness level) and then alphabetically.
#
# The classifications are based on the license classifier tool available at:
# https://github.com/google/licenseclassifier/blob/main/license_type.go
# Unfortunately, this open source version is no longer maintained.
# These are the differrent classifications we identify, ordered by restrictiveness level:
# * unencumbered, permissive, notice, reciprocal, restricted, by_exception_only, forbidden.
#
# 'by_exception_only' and 'forbidden' should never enter Chromium, reach out to
# product counsel if the need arises.
#
# REVIEW INSTRUCTIONS FOR chromium-third-party@google.com (and a guide to contributing to this file):
# 1. Paste the contents of the license to be classified into
#   https://opensource.corp.google.com/license/analyze. This will provide the ID
#   and the classification. Command line alternatives are documented at
#   go/license-classifier, but work on entire files only.
#   1.1 'unencumbered', 'permissive', or 'notice' are allowed ✅.
#   1.2 'reciprocal' are allowed, but only in open source projects e.g. Chromium.
#       See OPEN_SOURCE_SPDX_LICENSES below.
#   1.3 >='restricted' are handled on a case-by-case basis and require individual approval
#       from opensource-licensing@google.com and chromium-third-party@google.com. Be sure to include
#       the license and relevant details in the email. It can be helpful to
#       identify existing dependencies that have already been approved.
#
# 2. Check spdx.org/licenses to see if the license has an SPDX identifier.
#   2.1 If it does: Use this value instead of the license classifier output,
#       and add it to ALLOWED_SPDX_LICENSES.
#   2.2 If does not: Add the id provided by the license classifier
#       to EXTENDED_LICENSE_CLASSIFIERS.
#
# 3. Ensure that it is added under the correct classification
#   e.g. '# notice', and then sorted alphabetically asscending.
#
# 4. If you are uncertain whether a given third-party library can be included in
#   Chromium, please email opensource-licensing@google.com with the library's
#   license documentation, and explain where and how the component is going to
#   be used.
#
# 5. Note:
#   * Remove 'LicenseRef-' prefix from license classifier outputs.
#   * Case does not matter.
import json
import logging
import os
import subprocess
from typing import Optional

_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
# The repo's root directory.
_ROOT_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))

RESTRICTED_APPROVAL_FILENAME = "restrictive_license_approval.textproto"

STATUS_ALLOWED = "ALLOWED"
STATUS_APPROVED = "APPROVED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_RECIPROCAL_NOT_ALLOWED = "RECIPROCAL_NOT_ALLOWED"

_ALLOWED_SPDX_LICENSES = frozenset([
    # unencumbered.
    # go/keep-sorted start case=no
    "blessing",
    "CC0-1.0",
    "LZMA-SDK-9.22",
    "Unlicense",
    # go/keep-sorted end
    # permissive.
    # go/keep-sorted start case=no
    "0BSD",
    "bcrypt-Solar-Designer",
    "FSFUL",
    "GPL-2.0-with-autoconf-exception",
    "GPL-2.0-with-classpath-exception",
    "GPL-3.0-with-autoconf-exception",
    "MIT-0",
    # go/keep-sorted end
    # notice.
    # go/keep-sorted start case=no
    "AML",
    "Apache-2.0",
    "Artistic-1.0-Perl",
    "Artistic-2.0",
    "Beerware",
    "BSD-2-Clause",
    "BSD-2-Clause-FreeBSD",
    "BSD-3-Clause",
    "BSD-3-Clause-Attribution",
    "BSD-3-Clause-flex",
    "BSD-3-Clause-Open-MPI",
    "BSD-4-Clause",
    "BSD-4-Clause-UC",
    "BSD-4.3RENO",
    "BSD-4.3TAHOE",
    "BSD-Source-Code",
    "BSL-1.0",
    "CC-BY-3.0",
    "CC-BY-4.0",
    "CMU-Mach",
    "curl",
    "dtoa",
    "FSFAP",
    "FSFULLR",
    "FTL",
    "HPND",
    "HPND-sell-variant",
    "ICU",
    "IJG",
    "ISC",
    "JSON",
    "Libpng",
    "libpng-2.0",
    "libtiff",
    "Martin-Birgmeier",
    "Minpack",
    "MIT",
    "MIT-Khronos-old",
    "MIT-Modern-Variant",
    "MS-PL",
    "NAIST-2003",
    "NCSA",
    "OFL-1.1",
    "OpenSSL",
    "Python-2.0",
    "SGI-B-2.0",
    "Spencer-86",
    "SunPro",
    "TU-Berlin-1.0",
    "Unicode-3.0",
    "Unicode-DFS-2015",
    "Unicode-DFS-2016",
    "Unicode-TOU",
    "X11",
    "Zlib",
    # go/keep-sorted end
])

# These are licenses that are not in the SPDX license list, but are identified
# by the license classifier.
_EXTENDED_LICENSE_CLASSIFIERS = frozenset([
    # unencumbered.
    # go/keep-sorted start case=no
    "AhemFont",
    "Android-SDK",
    "LZMA",
    "Public Domain",
    "Public-Domain-ftglue",
    "Public-Domain-Gutenberg",
    "public-domain-md5",
    "Public-Domain-Ross-Williams",
    "Public-Domain-Sigslot",
    "Public-Domain-SpanDSP",
    "SPL-SQRT-FLOOR",
    # go/keep-sorted end
    # permissive.
    # go/keep-sorted start case=no
    "AMSFonts-2.2",
    "ietf",
    "RFC",
    "SolarDesigner",
    "test_fonts",
    # go/keep-sorted end
    # notice.
    # go/keep-sorted start case=no
    "Apache-with-LLVM-Exception",
    "Apache-with-Runtime-Exception",
    "base64",
    "base64-cpp",
    "Bitstream",
    "BLAS",
    "BSD-2-Clause-Flex",
    "BSD-3-Clause-OpenMPI",
    "BSD-4-Clause-Wasabi",
    "Caffe",
    "CERN",
    "dso",
    "Entenssa",
    "FFT2D",
    "getopt",
    "GIF-Encoder",
    "GNU-All-permissive-Copying-License",
    "IBM-DHCP",
    "JsonCPP",
    "Khronos",
    "Libpng-2.0",
    "OpenGLUT",
    "pffft",
    "PngSuite",
    "Punycode",
    "Scala",
    "SSLeay",
    "takuya-ooura",
    "unicode_org",
    "WebM-Project-Patent",
    "X11-Lucent",
    "zxing",
    # go/keep-sorted end

    # The Android Software Development Kit License is a special case.
    # It can introduce licensing complexities due to the potentially extensive
    # transitive dependency chain. Developers should carefully review the
    # licenses of all dependencies.
    "Android Software Development Kit License",
])

# These licenses are only allowed in open source projects due to their
# reciprocal requirements.
_OPEN_SOURCE_SPDX_LICENSES = frozenset([
    # reciprocal.
    # go/keep-sorted start case=no
    "APSL-2.0",
    "CDDL-1.0",
    "CDDL-1.1",
    "CPL-1.0",
    "EPL-1.0",
    "EPL-2.0",
    "MPL-1.1",
    "MPL-2.0",
    # go/keep-sorted end
])

# TODO(b/388620886): Implement warning when changing to or from these licenses
# (but not every time the README.chromium file is modified).
_WITH_PERMISSION_ONLY = frozenset([
    # restricted.
    # go/keep-sorted start case=no
    "CC-BY-SA-3.0",
    "GPL-2.0",
    "GPL-3.0",
    "LGPL-2.0",
    "LGPL-2.1",
    "LGPL-3.0",
    "NPL-1.1",
    # go/keep-sorted end
    # by_exception_only.
    # go/keep-sorted start case=no
    "Alliance-for-Open-Media-Patent",
    "Commercial",
    "MicrosoftEnterpriseWindowsDriverKit",
    "Opus-Patent-BSD-3-Clause",
    "Play-Core-SDK-TOS",
    "Unity-Companion-License-1.3",
    "UnRAR",
    # go/keep-sorted end
    # Patent files are special, and must be handled on a case by case basis.
    "Patent",
])

# These are references to files that are not licenses, but are allowed to be
# included in the LICENSE field.
_ALLOWED_REFERENCES = frozenset([
    "Refer to additional_readme_paths.json",
])

_ALLOWED_LICENSES = (_ALLOWED_SPDX_LICENSES
                     | _EXTENDED_LICENSE_CLASSIFIERS
                     | _ALLOWED_REFERENCES)
_ALLOWED_OPEN_SOURCE_LICENSES = _ALLOWED_LICENSES | _OPEN_SOURCE_SPDX_LICENSES
_ALL_LICENSES = _ALLOWED_OPEN_SOURCE_LICENSES | _WITH_PERMISSION_ONLY


# TODO(https://crbug.com/452151523): Remove this after migrating downstream
# clients to use exported functions below.
ALLOWED_SPDX_LICENSES = _ALLOWED_SPDX_LICENSES
EXTENDED_LICENSE_CLASSIFIERS = _EXTENDED_LICENSE_CLASSIFIERS
OPEN_SOURCE_SPDX_LICENSES = _OPEN_SOURCE_SPDX_LICENSES
WITH_PERMISSION_ONLY = _WITH_PERMISSION_ONLY


def normalize_value(value: str) -> str:
    """Removes unnecessary prefixes/suffixes.
    """
    # Do not convert to lower case here, as we want to preserve the original
    # casing for warning messages.
    return value.strip().removeprefix("LicenseRef-")


def _license_in_list(value: str, allow_list: frozenset[str]) -> bool:
    """Normalizes and does a case insensitive check if value is in allow_list.
    """
    return normalize_value(value).lower() in map(str.lower, allow_list)


def is_a_known_license(value: str) -> bool:
    return _license_in_list(value, _ALL_LICENSES)


def is_allowed_spdx_license(value: str) -> bool:
    return _license_in_list(value, _ALLOWED_SPDX_LICENSES)


def is_extended_license_classifier(value: str) -> bool:
    return _license_in_list(value, _EXTENDED_LICENSE_CLASSIFIERS)


def is_allowed_license(value: str) -> bool:
    return _license_in_list(value, _ALLOWED_LICENSES)


def is_open_source_license(value: str) -> bool:
    return _license_in_list(value, _OPEN_SOURCE_SPDX_LICENSES)


def is_with_permission_only(value: str) -> bool:
    return _license_in_list(value, _WITH_PERMISSION_ONLY)


def is_license_allowed(value: str,
                       is_open_source_project: bool = False) -> bool:
    """Returns whether the value is in the allowlist for license
    types.
    """
    # Restricted licenses are not enforced by presubmits, see b/388620886 😢.
    if is_with_permission_only(value):
        return True
    if is_allowed_license(value):
        return True
    if is_open_source_project and is_open_source_license(value):
        return True
    return False


def load_restrictive_license_approval_textproto(path: str) -> dict[str, int]:
    """Loads a restrictive_license_approval.textproto file and returns a mapping of license IDs to bug IDs."""
    covered = {}
    script_path = os.path.join(_ROOT_DIR, "metadata", "scripts",
                               "parse_restrictive_license_approval.py")
    stdout = subprocess.check_output(["vpython3", script_path,
                                      path]).decode("utf-8")
    approvals = json.loads(stdout)
    for approval in approvals:
        license_id = approval.get("id")
        bug = approval.get("bug")
        # Ignore entries that don't have both an id and bug.
        if not license_id or not bug:
            continue
        covered[license_id.lower()] = bug
        covered[normalize_value(license_id).lower()] = bug
    return covered


def get_license_validation_status(
        license_value: str,
        source_file_dir: Optional[str] = None,
        is_open_source_project: bool = True,
        android_compatible: Optional[str] = None) -> str:
    """Evaluates the validation status of a license value.

    Returns 'ALLOWED' if all licenses are allowed, or a combination of:
    - 'UNKNOWN[list, of, licenseIDs, ...]'
    - 'RECIPROCAL_NOT_ALLOWED[list, of, licenseIDs, ...]'
    - 'APPROVED[(restricted-license, b/approval_bug_number), ...]'

    Args:
      license_value: The license field value (e.g., "MIT, GPL-2.0").
      source_file_dir: Directory containing the local approval textproto.
      is_open_source_project: Whether the project is open source (reciprocal
        licenses are disallowed in non-open-source projects).
      android_compatible: Optional string value of 'License Android Compatible' field.
    """
    if not license_value:
        return STATUS_UNKNOWN

    licenses = [normalize_value(val) for val in license_value.split(",")]

    # Map normalized_lic_id -> bug_id.
    approvals = None
    unknown_licenses = []
    approved_licenses = []
    reciprocal_not_allowed_licenses = []

    for license in licenses:
        # Check if globally allowed.
        if is_license_allowed(license, is_open_source_project):
            continue

        # Reciprocal in internal requires 'Android Compatible = yes'.
        # This indicates alternative arrangements have been made to meet the
        # reciprocal obligations of the license.
        is_reciprocal = is_open_source_license(license)
        if is_reciprocal:
            if (not android_compatible
                    or android_compatible.lower().strip() != "yes"):
                reciprocal_not_allowed_licenses.append(license)
            continue

        # Source dir is required to check restrictive_license_approval.textproto.
        if not source_file_dir:
            unknown_licenses.append(license)
            continue

        # Look for a restrictive license approval if it's not in the allowlist.
        if approvals is None:
            approvals = {}
            restricted_approval_filepath = os.path.join(
                source_file_dir, RESTRICTED_APPROVAL_FILENAME)
            if os.path.isfile(restricted_approval_filepath):
                approvals = load_restrictive_license_approval_textproto(
                    restricted_approval_filepath)

        lic_norm = normalize_value(license).lower()

        # Check if approved.
        bug = None
        is_approved = False
        if lic_norm in approvals:
            bug = approvals[lic_norm]
            is_approved = True

        if is_approved:
            approved_licenses.append((license, bug))
        else:
            unknown_licenses.append(license)

    # Construct status string.
    if not unknown_licenses and not approved_licenses and not reciprocal_not_allowed_licenses:
        return STATUS_ALLOWED

    parts = []
    if unknown_licenses:
        parts.append(f"{STATUS_UNKNOWN}[{', '.join(unknown_licenses)}]")

    if reciprocal_not_allowed_licenses:
        parts.append(
            f"{STATUS_RECIPROCAL_NOT_ALLOWED}[{', '.join(reciprocal_not_allowed_licenses)}]"
        )

    if approved_licenses:
        approval_strings = []
        for lic, bug in approved_licenses:
            bug_str = f"b/{bug}" if bug else "N/A"
            approval_strings.append(f"({lic}, {bug_str})")
        parts.append(f"{STATUS_APPROVED}[{', '.join(approval_strings)}]")

    return ", ".join(parts)

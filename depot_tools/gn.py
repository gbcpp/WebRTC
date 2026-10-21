#!/usr/bin/env python3
# Copyright 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This script is a wrapper around the GN binary that is pulled from Google
Cloud Storage when you sync Chrome. The binaries go into platform-specific
subdirectories in the source tree.

This script makes there be one place for forwarding to the correct platform's
binary. It will also automatically try to find the gn binary when run inside
the chrome source tree, so users can just type "gn" on the command line
(normally depot_tools is on the path)."""

import gclient_paths
import os
import subprocess
import sys


def PruneVirtualEnv():
    # Set by VirtualEnv, no need to keep it.
    os.environ.pop('VIRTUAL_ENV', None)

    # Set by VPython, if scripts want it back they have to set it explicitly.
    os.environ.pop('PYTHONNOUSERSITE', None)

    # Look for "activate_this.py" in this path, which is installed by
    # VirtualEnv. This mechanism is used by vpython as well to sanitize
    # VirtualEnvs from $PATH.
    os.environ['PATH'] = os.pathsep.join([
        p for p in os.environ.get('PATH', '').split(os.pathsep)
        if not os.path.isfile(os.path.join(p, 'activate_this.py'))
    ])


def FindGnTool():
    # Try in primary solution location first, with the gn binary having been
    # downloaded by cipd in the projects DEPS.
    primary_solution_path = gclient_paths.GetPrimarySolutionPath()
    if primary_solution_path:
        gn_path = os.path.join(primary_solution_path, 'third_party', 'gn',
                               'gn' + gclient_paths.GetExeSuffix())
        if os.path.exists(gn_path):
            return gn_path

    # Otherwise try the old .sha1 and download_from_google_storage locations
    # inside of buildtools.
    bin_path = gclient_paths.GetBuildtoolsPlatformBinaryPath()
    if not bin_path:
        gn_path = gclient_paths.FindInPath('gn')
        if gn_path:
            return gn_path
        print('gn.py: Unable to find gn in your $PATH', file=sys.stderr)
        print('Hint: `which -a gn` should output two entries', file=sys.stderr)
        return None
    if os.environ.get('CHROMIUM_BUILDTOOLS_PATH'):
        print('Using $CHROMIUM_BUILDTOOLS_PATH to find gn. ' +
              'CHROMIUM_BUILDTOOLS_PATH is highly unsupported ' +
              'and may break gn.',
              file=sys.stderr)

    # TODO(b/328065301): Once chromium/src CL has landed to migrate
    # buildtools/<platform>/gn to buildtools/<platform>/gn/gn, only return
    # gn/gn path.
    old_gn_path = os.path.join(bin_path, 'gn' + gclient_paths.GetExeSuffix())
    new_gn_path = os.path.join(bin_path, 'gn',
                               'gn' + gclient_paths.GetExeSuffix())
    paths = [new_gn_path, old_gn_path]
    for path in paths:
        if os.path.isfile(path):
            return path
    print('gn.py: Could not find gn executable at: %s' % paths, file=sys.stderr)
    print(
        "Either GN isn't installed on your system, or you're not running in " +
        "a checkout with a preinstalled gn binary.",
        file=sys.stderr)


def main(args):
    # Prune all evidence of VPython/VirtualEnv out of the environment. This
    # means that we 'unwrap' vpython VirtualEnv path/env manipulation.
    # Invocations of `python` from GN should never inherit the gn.py's own
    # VirtualEnv. This also helps to ensure that generated ninja files do not
    # reference python.exe from the VirtualEnv generated from depot_tools' own
    # .vpython3 file (or lack thereof), but instead reference the default python
    # from the PATH.
    PruneVirtualEnv()
    gn = FindGnTool()
    if gn:
        return subprocess.call([gn] + args[1:])
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        sys.stderr.write('interrupted\n')
        sys.exit(1)

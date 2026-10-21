# Copyright (c) 2025 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import json
import os
import re
import tempfile

import gclient_utils
import lockfile
import scm


@contextlib.contextmanager
def _AtomicFileWriter(path, mode='w'):
    """Atomic file writer context manager."""
    # Create temp file in same directory to ensure atomic rename works
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path),
                                     text='b' not in mode)
    try:
        with os.fdopen(fd, mode) as f:
            yield f
        # Atomic rename
        gclient_utils.safe_replace(temp_path, path)
    except Exception:
        # Cleanup on failure
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


class GerritCache(object):
    """Simple JSON file-based cache for Gerrit API results."""

    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.cache_path = self._get_cache_path()

    @staticmethod
    def get_repo_code_owners_enabled_key(host, project):
        return 'code-owners.%s.%s.enabled' % (host, project)

    @staticmethod
    def get_host_code_owners_enabled_key(host):
        return 'code-owners.%s.enabled' % host

    def _get_cache_path(self):
        path = os.environ.get('DEPOT_TOOLS_GERRIT_CACHE_PATH')
        if path:
            return path

        try:
            path = scm.GIT.GetConfig(self.root_dir,
                                     'depot-tools.gerrit-cache-path')
            if path:
                return path
        except Exception:
            pass

        try:
            if self.root_dir:
                # Use a deterministic name based on the repo path
                sanitized_path = re.sub(r'[^a-zA-Z0-9]', '_',
                                        os.path.abspath(self.root_dir))
                filename = 'depot_tools_gerrit_cache_%s.json' % sanitized_path
                path = os.path.join(tempfile.gettempdir(), filename)
            else:
                fd, path = tempfile.mkstemp(prefix='depot_tools_gerrit_cache_',
                                            suffix='.json')
                os.close(fd)

            if not os.path.exists(path):
                # Initialize with empty JSON object
                with open(path, 'w') as f:
                    json.dump({}, f)

            try:
                scm.GIT.SetConfig(self.root_dir,
                                  'depot-tools.gerrit-cache-path', path)
            except Exception:
                # If we can't set config (e.g. not a git repo and no env var
                # set), just return the temp path. It will be a per-process
                # cache in that case.
                pass
            return path
        except Exception:
            # Fallback to random temp file if everything else fails
            fd, path = tempfile.mkstemp(prefix='gerrit_cache_', suffix='.json')
            os.close(fd)
            return path

    def get(self, key):
        if not self.cache_path:
            return None
        try:
            with lockfile.lock(self.cache_path, timeout=1):
                if os.path.exists(self.cache_path):
                    with open(self.cache_path, 'r') as f:
                        try:
                            data = json.load(f)
                            return data.get(key)
                        except ValueError:
                            # Corrupt cache file, treat as miss
                            return None
        except Exception:
            # Ignore cache errors
            return None

    def set(self, key, value):
        if not self.cache_path:
            return
        try:
            with lockfile.lock(self.cache_path, timeout=1):
                data = {}
                if os.path.exists(self.cache_path):
                    with open(self.cache_path, 'r') as f:
                        try:
                            data = json.load(f)
                        except ValueError:
                            # Corrupt cache, start fresh
                            data = {}
                data[key] = value
                with _AtomicFileWriter(self.cache_path, 'w') as f:
                    json.dump(data, f)
        except Exception:
            # Ignore cache errors
            pass

    def getBoolean(self, key):
        """Returns the value for key as a boolean, or None if missing."""
        val = self.get(key)
        if val is None:
            return None
        return bool(val)

    def setBoolean(self, key, value):
        """Sets the value for key as a boolean."""
        self.set(key, bool(value))

#!/usr/bin/env vpython3
# Copyright (c) 2025 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import gerrit_cache
import unittest.mock as mock


class AtomicFileWriterTest(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir)

    def testSuccess(self):
        path = os.path.join(self.test_dir, 'test_file')
        with gerrit_cache._AtomicFileWriter(path, 'w') as f:
            f.write('content')

        self.assertTrue(os.path.exists(path))
        with open(path, 'r') as f:
            self.assertEqual(f.read(), 'content')

    def testFailure(self):
        path = os.path.join(self.test_dir, 'test_file')
        try:
            with gerrit_cache._AtomicFileWriter(path, 'w') as f:
                f.write('content')
                raise Exception('oops')
        except Exception:
            pass

        self.assertFalse(os.path.exists(path))

    def testOverwrite(self):
        path = os.path.join(self.test_dir, 'test_file')
        with open(path, 'w') as f:
            f.write('old')

        with gerrit_cache._AtomicFileWriter(path, 'w') as f:
            f.write('new')

        with open(path, 'r') as f:
            self.assertEqual(f.read(), 'new')

    def testOverwriteFailure(self):
        path = os.path.join(self.test_dir, 'test_file')
        with open(path, 'w') as f:
            f.write('old')

        try:
            with gerrit_cache._AtomicFileWriter(path, 'w') as f:
                f.write('new')
                raise Exception('oops')
        except Exception:
            pass

        with open(path, 'r') as f:
            self.assertEqual(f.read(), 'old')


class GerritCacheTest(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir)
        self.mock_git = mock.patch('gerrit_cache.scm.GIT').start()
        self.addCleanup(mock.patch.stopall)
        self.mock_git.GetConfig.return_value = None

    def testGetSet(self):
        cache = gerrit_cache.GerritCache(self.test_dir)
        cache.set('key', 'value')
        self.assertEqual(cache.get('key'), 'value')

        # Verify persistence
        cache2 = gerrit_cache.GerritCache(self.test_dir)
        self.assertEqual(cache2.get('key'), 'value')

    def testGetSetBoolean(self):
        cache = gerrit_cache.GerritCache(self.test_dir)
        cache.setBoolean('bool_key', True)
        self.assertTrue(cache.getBoolean('bool_key'))

        cache2 = gerrit_cache.GerritCache(self.test_dir)
        self.assertTrue(cache2.getBoolean('bool_key'))

    def testGetMissing(self):
        cache = gerrit_cache.GerritCache(self.test_dir)
        self.assertIsNone(cache.get('missing'))

    def testCachePathFromEnv(self):
        with mock.patch.dict(
                os.environ, {
                    'DEPOT_TOOLS_GERRIT_CACHE_PATH':
                    os.path.join(self.test_dir, 'env_cache.json')
                }):
            cache = gerrit_cache.GerritCache(self.test_dir)
            cache.set('key', 'env_value')
            self.assertEqual(cache.get('key'), 'env_value')
            self.assertTrue(
                os.path.exists(os.path.join(self.test_dir, 'env_cache.json')))

    def testCachePathFromGitConfig(self):
        config_path = os.path.join(self.test_dir, 'config_cache.json')
        self.mock_git.GetConfig.return_value = config_path
        cache = gerrit_cache.GerritCache(self.test_dir)
        self.assertEqual(cache.cache_path, config_path)

    def testCachePathCreation(self):
        # When no env var and no config, it should create a deterministic temp file and set config
        cache = gerrit_cache.GerritCache(self.test_dir)
        sanitized_path = re.sub(r'[^a-zA-Z0-9]', '_',
                                os.path.abspath(self.test_dir))
        expected_filename = 'depot_tools_gerrit_cache_%s.json' % sanitized_path
        self.assertTrue(cache.cache_path.endswith(expected_filename))
        self.assertTrue(cache.cache_path.startswith(tempfile.gettempdir()))
        self.mock_git.SetConfig.assert_called_with(
            self.test_dir, 'depot-tools.gerrit-cache-path', cache.cache_path)

    def testCachePathCreationLinux(self):
        root_dir = '/usr/local/google/home/user/repo'
        with mock.patch('os.path.abspath', return_value=root_dir):
            cache = gerrit_cache.GerritCache(root_dir)
            sanitized_path = re.sub(r'[^a-zA-Z0-9]', '_', root_dir)
            expected_filename = 'depot_tools_gerrit_cache_%s.json' % sanitized_path
            self.assertTrue(cache.cache_path.endswith(expected_filename))

    def testCachePathCreationWindows(self):
        root_dir = r'C:\Users\user\repo'
        # On Linux, os.path.abspath('C:\Users\user\repo') will prepend current cwd.
        with mock.patch('os.path.abspath', return_value=root_dir):
            cache = gerrit_cache.GerritCache(root_dir)
            sanitized_path = re.sub(r'[^a-zA-Z0-9]', '_', root_dir)
            expected_filename = 'depot_tools_gerrit_cache_%s.json' % sanitized_path
            self.assertTrue(cache.cache_path.endswith(expected_filename))

    def testCorruptCache(self):
        cache = gerrit_cache.GerritCache(self.test_dir)
        # Write garbage to the cache file
        with open(cache.cache_path, 'w') as f:
            f.write('this is not json')

        # Should not crash, just return None
        self.assertIsNone(cache.get('key'))

        cache.set('key', 'value')
        self.assertEqual(cache.get('key'), 'value')


if __name__ == "__main__":
    unittest.main()

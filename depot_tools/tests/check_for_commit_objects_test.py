#!/usr/bin/env python3
# Copyright (c) 2025 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import sys
import unittest
from unittest import mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import presubmit_canned_checks
from testing_support.presubmit_canned_checks_test_mocks import MockInputApi, MockOutputApi, MockFile


class MockRelativeFile(MockFile):

    def __init__(self, rel_path, new_contents):
        # We pass absolute path to super so AbsoluteLocalPath returns absolute path
        abs_path = os.path.join('/tmp/repo', rel_path)
        super(MockRelativeFile, self).__init__(abs_path, new_contents)
        self._rel_path = rel_path

    def LocalPath(self):
        return self._rel_path


class CheckForCommitObjectsTest(unittest.TestCase):

    def setUp(self):
        self.input_api = MockInputApi()
        self.output_api = MockOutputApi()
        self.input_api.change.RepositoryRoot = lambda: '/tmp/repo'
        self.input_api.PresubmitLocalPath = lambda: '/tmp/repo'
        self.input_api.change.scm = 'git'

        # Patch ParseDeps to avoid reading DEPS file
        self.patcher = mock.patch('presubmit_canned_checks._ParseDeps')
        self.mock_parse_deps = self.patcher.start()
        self.mock_parse_deps.return_value = {'git_dependencies': 'DEPS'}

    def tearDown(self):
        self.patcher.stop()

    def testBatchedExecutionSmallCL(self):
        # 2 files, should run batched git ls-tree
        self.input_api.files = [
            MockFile(os.path.join('/tmp/repo', 'a.txt'), []),
            MockFile(os.path.join('/tmp/repo', 'b.txt'), [])
        ]

        # Mock check_output
        self.input_api.subprocess.check_output = mock.Mock(return_value=b'')

        presubmit_canned_checks.CheckForCommitObjects(self.input_api,
                                                      self.output_api)

        # Verify check_output was called with specific files
        args = self.input_api.subprocess.check_output.call_args[0][0]
        self.assertIn('ls-tree', args)
        self.assertIn('a.txt', args)
        self.assertIn('b.txt', args)
        self.assertIn('--full-tree', args)

    def testFullTreeExecutionLargeCL(self):
        # 1001 files, should run full tree scan
        self.input_api.files = [
            MockFile(os.path.join('/tmp/repo', f'f{i}.txt'), [])
            for i in range(1001)
        ]

        # Mock check_output
        self.input_api.subprocess.check_output = mock.Mock(return_value=b'')

        presubmit_canned_checks.CheckForCommitObjects(self.input_api,
                                                      self.output_api)

        # Verify check_output was called with --full-tree
        args = self.input_api.subprocess.check_output.call_args[0][0]
        self.assertIn('ls-tree', args)
        self.assertIn('--full-tree', args)
        self.assertNotIn('f0.txt', args)

    def testFullTreeExecutionWhenDepsModified(self):
        # Small CL but DEPS is modified, should run full tree scan
        self.input_api.files = [
            MockRelativeFile('DEPS', []),
            MockRelativeFile('other.txt', [])
        ]

        self.input_api.subprocess.check_output = mock.Mock(return_value=b'')

        presubmit_canned_checks.CheckForCommitObjects(self.input_api,
                                                      self.output_api)

        args = self.input_api.subprocess.check_output.call_args[0][0]
        self.assertIn('ls-tree', args)
        self.assertIn('--full-tree', args)
        # Should not list specific files when running full tree
        self.assertNotIn('other.txt', args)

    def testBatchedFoundCommit(self):
        # 1 submodule, found a commit object (gitlink)
        self.input_api.files = []

        # Mock AffectedSubmodules to return the submodule
        submodule_file = MockFile(os.path.join('/tmp/repo', 'submodule'), [])
        self.input_api.change.AffectedSubmodules = mock.Mock(
            return_value=[submodule_file])

        # Mock output: 160000 commit <hash>\tsubmodule
        # NOTE: The loop in CheckForCommitObjects looks for _GIT_MODE_SUBMODULE (b'160000')
        self.input_api.subprocess.check_output = mock.Mock(
            return_value=(b'160000 commit 1234567890abcdef\tsubmodule\0'))

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(len(results), 1)
        self.assertIn('submodule', results[0].message)

    def testBatchedExecutionWithSubmodule(self):
        # 1 file + 1 submodule, should run batched git ls-tree with both
        self.input_api.files = [
            MockFile(os.path.join('/tmp/repo', 'a.txt'), []),
        ]

        # Mock AffectedSubmodules to return the submodule
        submodule_file = MockFile(os.path.join('/tmp/repo', 'third_party/perl'),
                                  [])
        self.input_api.change.AffectedSubmodules = mock.Mock(
            return_value=[submodule_file])

        # Mock check_output
        self.input_api.subprocess.check_output = mock.Mock(return_value=b'')

        presubmit_canned_checks.CheckForCommitObjects(self.input_api,
                                                      self.output_api)

        # Verify check_output was called with both files
        args = self.input_api.subprocess.check_output.call_args[0][0]
        self.assertIn('ls-tree', args)
        self.assertIn('a.txt', args)
        self.assertIn('third_party/perl', args)
        self.assertIn('--full-tree', args)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
# Copyright (c) 2021 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os.path
import subprocess
import sys
import unittest
from unittest import mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from testing_support.presubmit_canned_checks_test_mocks import (
    MockFile, MockAffectedFile, MockInputApi, MockOutputApi, MockChange)

import presubmit_canned_checks

# TODO: Should fix these warnings.
# pylint: disable=line-too-long


class InclusiveLanguageCheckTest(unittest.TestCase):
    def testBlockedTerms(self):
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        input_api.presubmit_local_path = ''

        input_api.files = [
            MockFile(
                os.path.normpath(
                    'infra/inclusive_language_presubmit_exempt_dirs.txt'), [
                        'some/dir 2 1',
                        'some/other/dir 2 1',
                    ]),
            MockFile(
                os.path.normpath('some/ios/file.mm'),
                [
                    'TEST(SomeClassTest, SomeInteraction, blacklist) {',  # nocheck
                    '}'
                ]),
            MockFile(
                os.path.normpath('some/mac/file.mm'),
                [
                    'TEST(SomeClassTest, SomeInteraction, BlackList) {',  # nocheck
                    '}'
                ]),
            MockFile(os.path.normpath('another/ios_file.mm'),
                     ['class SomeTest : public testing::Test blocklist {};']),
            MockFile(os.path.normpath('some/ios/file_egtest.mm'),
                     ['- (void)testSomething { V(whitelist); }']),  # nocheck
            MockFile(
                os.path.normpath('some/ios/file_unittest.mm'),
                ['TEST_F(SomeTest, Whitelist) { V(allowlist); }']),  # nocheck
            MockFile(
                os.path.normpath('some/doc/file.md'),
                [
                    '# Title',
                    'Some markdown text includes master.',  # nocheck
                ]),
            MockFile(
                os.path.normpath('some/doc/ok_file.md'),
                [
                    '# Title',
                    # This link contains a '//' which the matcher thinks is a
                    # C-style comment, and the 'master' term appears after the
                    # '//' in the URL, so it gets ignored as a side-effect.
                    '[Ignored](https://git/project.git/+/master/foo)',  # nocheck
                ]),
            MockFile(
                os.path.normpath('some/doc/branch_name_file.md'),
                [
                    '# Title',
                    # Matches appearing before `//` still trigger the check.
                    '[src/master](https://git/p.git/+/master/foo)',  # nocheck
                ]),
            MockFile(
                os.path.normpath('some/java/file/TestJavaDoc.java'),
                [
                    '/**',
                    ' * This line contains the word master,',  # nocheck
                    '* ignored because this is a comment. See {@link',
                    ' * https://s/src/+/master:tools/README.md}',  # nocheck
                    ' */'
                ]),
            MockFile(
                os.path.normpath('some/java/file/TestJava.java'),
                [
                    'class TestJava {',
                    '  public String master;',  # nocheck
                    '}'
                ]),
            MockFile(
                os.path.normpath('some/html/file.html'),
                [
                    '<-- an existing html multiline comment',
                    'says "master" here',  # nocheck
                    'in the comment -->'
                ])
        ]

        errors = presubmit_canned_checks.CheckInclusiveLanguage(
            input_api, MockOutputApi())
        self.assertEqual(1, len(errors))
        self.assertTrue(
            os.path.normpath('some/ios/file.mm') in errors[0].message)
        self.assertTrue(
            os.path.normpath('another/ios_file.mm') not in errors[0].message)
        self.assertTrue(
            os.path.normpath('some/mac/file.mm') in errors[0].message)
        self.assertTrue(
            os.path.normpath('some/ios/file_egtest.mm') in errors[0].message)
        self.assertTrue(
            os.path.normpath('some/ios/file_unittest.mm') in errors[0].message)
        self.assertTrue(
            os.path.normpath('some/doc/file.md') not in errors[0].message)
        self.assertTrue(
            os.path.normpath('some/doc/ok_file.md') not in errors[0].message)
        self.assertTrue(
            os.path.normpath('some/doc/branch_name_file.md') not in
            errors[0].message)
        self.assertTrue(
            os.path.normpath('some/java/file/TestJavaDoc.java') not in
            errors[0].message)
        self.assertTrue(
            os.path.normpath('some/java/file/TestJava.java') not in
            errors[0].message)
        self.assertTrue(
            os.path.normpath('some/html/file.html') not in errors[0].message)

    def testBlockedTermsWithLegacy(self):
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        input_api.presubmit_local_path = ''

        input_api.files = [
            MockFile(
                os.path.normpath(
                    'infra/inclusive_language_presubmit_exempt_dirs.txt'), [
                        'some/ios 2 1',
                        'some/other/dir 2 1',
                    ]),
            MockFile(
                os.path.normpath('some/ios/file.mm'),
                [
                    'TEST(SomeClassTest, SomeInteraction, blacklist) {',  # nocheck
                    '}'
                ]),
            MockFile(
                os.path.normpath('some/ios/subdir/file.mm'),
                [
                    'TEST(SomeClassTest, SomeInteraction, blacklist) {',  # nocheck
                    '}'
                ]),
            MockFile(
                os.path.normpath('some/mac/file.mm'),
                [
                    'TEST(SomeClassTest, SomeInteraction, BlackList) {',  # nocheck
                    '}'
                ]),
            MockFile(os.path.normpath('another/ios_file.mm'),
                     ['class SomeTest : public testing::Test blocklist {};']),
            MockFile(os.path.normpath('some/ios/file_egtest.mm'),
                     ['- (void)testSomething { V(whitelist); }']),  # nocheck
            MockFile(
                os.path.normpath('some/ios/file_unittest.mm'),
                ['TEST_F(SomeTest, Whitelist) { V(allowlist); }']),  # nocheck
        ]

        errors = presubmit_canned_checks.CheckInclusiveLanguage(
            input_api, MockOutputApi())
        self.assertEqual(1, len(errors))
        self.assertTrue(
            os.path.normpath('some/ios/file.mm') not in errors[0].message)
        self.assertTrue(
            os.path.normpath('some/ios/subdir/file.mm') in errors[0].message)
        self.assertTrue(
            os.path.normpath('another/ios_file.mm') not in errors[0].message)
        self.assertTrue(
            os.path.normpath('some/mac/file.mm') in errors[0].message)
        self.assertTrue(
            os.path.normpath('some/ios/file_egtest.mm') not in
            errors[0].message)
        self.assertTrue(
            os.path.normpath('some/ios/file_unittest.mm') not in
            errors[0].message)

    def testBlockedTermsWithNocheck(self):
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        input_api.presubmit_local_path = ''

        input_api.files = [
            MockFile(
                os.path.normpath(
                    'infra/inclusive_language_presubmit_exempt_dirs.txt'), [
                        'some/dir 2 1',
                        'some/other/dir 2 1',
                    ]),
            MockFile(
                os.path.normpath('some/ios/file.mm'),
                [
                    'TEST(SomeClassTest, SomeInteraction, ',
                    ' blacklist) { // nocheck',  # nocheck
                    '}'
                ]),
            MockFile(
                os.path.normpath('some/mac/file.mm'),
                [
                    'TEST(SomeClassTest, SomeInteraction, ',
                    'BlackList) { // nocheck',  # nocheck
                    '}'
                ]),
            MockFile(os.path.normpath('another/ios_file.mm'),
                     ['class SomeTest : public testing::Test blocklist {};']),
            MockFile(os.path.normpath('some/ios/file_egtest.mm'),
                     ['- (void)testSomething { ', 'V(whitelist); } // nocheck'
                      ]),  # nocheck
            MockFile(
                os.path.normpath('some/ios/file_unittest.mm'),
                [
                    'TEST_F(SomeTest, Whitelist) // nocheck',  # nocheck
                    ' { V(allowlist); }'
                ]),
            MockFile(
                os.path.normpath('some/doc/file.md'),
                [
                    'Master in markdown <!-- nocheck -->',  # nocheck
                    '## Subheading is okay'
                ]),
            MockFile(
                os.path.normpath('some/java/file/TestJava.java'),
                [
                    'class TestJava {',
                    '  public String master; // nocheck',  # nocheck
                    '}'
                ]),
            MockFile(
                os.path.normpath('some/html/file.html'),
                [
                    '<-- an existing html multiline comment',
                    'says "master" here --><!-- nocheck -->',  # nocheck
                    '<!-- in the comment -->'
                ])
        ]

        errors = presubmit_canned_checks.CheckInclusiveLanguage(
            input_api, MockOutputApi())
        self.assertEqual(0, len(errors))

    def testTopLevelDirExcempt(self):
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        input_api.presubmit_local_path = ''

        input_api.files = [
            MockFile(
                os.path.normpath(
                    'infra/inclusive_language_presubmit_exempt_dirs.txt'), [
                        '. 2 1',
                        'some/other/dir 2 1',
                    ]),
            MockFile(
                os.path.normpath('presubmit_canned_checks_test.py'),
                [
                    'TEST(SomeClassTest, SomeInteraction, blacklist) {',  # nocheck
                    '}'
                ]),
            MockFile(
                os.path.normpath('presubmit_canned_checks.py'),
                ['- (void)testSth { V(whitelist); } // nocheck']),  # nocheck
        ]

        errors = presubmit_canned_checks.CheckInclusiveLanguage(
            input_api, MockOutputApi())
        self.assertEqual(1, len(errors))
        self.assertTrue(
            os.path.normpath('presubmit_canned_checks_test.py') in
            errors[0].message)
        self.assertTrue(
            os.path.normpath('presubmit_canned_checks.py') not in
            errors[0].message)

    def testChangeIsForSomeOtherRepo(self):
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: 'v8'
        input_api.presubmit_local_path = ''

        input_api.files = [
            MockFile(
                os.path.normpath('some_file'),
                [
                    '# this is a blacklist',  # nocheck
                ]),
        ]
        errors = presubmit_canned_checks.CheckInclusiveLanguage(
            input_api, MockOutputApi())
        self.assertEqual([], errors)

    def testDirExemptWithComment(self):
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        input_api.presubmit_local_path = ''

        input_api.files = [
            MockFile(
                os.path.normpath(
                    'infra/inclusive_language_presubmit_exempt_dirs.txt'), [
                        '# this is a comment',
                        'dir1',
                        '# dir2',
                    ]),

            # this should be excluded
            MockFile(
                os.path.normpath('dir1/1.py'),
                [
                    'TEST(SomeClassTest, SomeInteraction, blacklist) {',  # nocheck
                    '}'
                ]),

            # this should not be excluded
            MockFile(os.path.normpath('dir2/2.py'),
                     ['- (void)testSth { V(whitelist); }']),  # nocheck
        ]

        errors = presubmit_canned_checks.CheckInclusiveLanguage(
            input_api, MockOutputApi())
        self.assertEqual(1, len(errors))
        self.assertTrue(os.path.normpath('dir1/1.py') not in errors[0].message)
        self.assertTrue(os.path.normpath('dir2/2.py') in errors[0].message)



class DescriptionChecksTest(unittest.TestCase):
    def testCheckDescriptionUsesColonInsteadOfEquals(self):
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        input_api.presubmit_local_path = ''

        # Verify error in case of the attempt to use "Bug=".
        input_api.change = MockChange([], 'Broken description\nBug=123')
        errors = presubmit_canned_checks.CheckDescriptionUsesColonInsteadOfEquals(
            input_api, MockOutputApi())
        self.assertEqual(1, len(errors))
        self.assertTrue('Bug=' in errors[0].message)

        # Verify error in case of the attempt to use "Fixed=".
        input_api.change = MockChange([], 'Broken description\nFixed=123')
        errors = presubmit_canned_checks.CheckDescriptionUsesColonInsteadOfEquals(
            input_api, MockOutputApi())
        self.assertEqual(1, len(errors))
        self.assertTrue('Fixed=' in errors[0].message)

        # Verify error in case of the attempt to use the lower case "bug=".
        input_api.change = MockChange([],
                                      'Broken description lowercase\nbug=123')
        errors = presubmit_canned_checks.CheckDescriptionUsesColonInsteadOfEquals(
            input_api, MockOutputApi())
        self.assertEqual(1, len(errors))
        self.assertTrue('Bug=' in errors[0].message)

        # Verify no error in case of "Bug:"
        input_api.change = MockChange([], 'Correct description\nBug: 123')
        errors = presubmit_canned_checks.CheckDescriptionUsesColonInsteadOfEquals(
            input_api, MockOutputApi())
        self.assertEqual(0, len(errors))

        # Verify no error in case of "Fixed:"
        input_api.change = MockChange([], 'Correct description\nFixed: 123')
        errors = presubmit_canned_checks.CheckDescriptionUsesColonInsteadOfEquals(
            input_api, MockOutputApi())
        self.assertEqual(0, len(errors))


class ChromiumDependencyMetadataCheckTest(unittest.TestCase):
    def testDefaultFileFilter(self):
        """Checks the default file filter limits the scope to Chromium dependency
        metadata files.
        """
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        input_api.files = [
            MockFile(os.path.normpath('foo/README.md'), ['Shipped: no?']),
            MockFile(os.path.normpath('foo/main.py'), ['Shipped: yes?']),
        ]
        results = presubmit_canned_checks.CheckChromiumDependencyMetadata(
            input_api, MockOutputApi())
        self.assertEqual(len(results), 0)

    def testSkipDeletedFiles(self):
        """Checks validation is skipped for deleted files."""
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        input_api.files = [
            MockFile(os.path.normpath('foo/README.chromium'), ['No fields'],
                     action='D'),
        ]
        results = presubmit_canned_checks.CheckChromiumDependencyMetadata(
            input_api, MockOutputApi())
        self.assertEqual(len(results), 0)

    def testFeedbackForNoMetadata(self):
        """Checks presubmit results are returned for files without any metadata."""
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        input_api.files = [
            MockFile(os.path.normpath('foo/README.chromium'), ['No fields']),
        ]
        results = presubmit_canned_checks.CheckChromiumDependencyMetadata(
            input_api, MockOutputApi())
        self.assertEqual(len(results), 1)
        self.assertTrue("No dependency metadata" in results[0].message)

    def testFeedbackForInvalidMetadata(self):
        """Checks presubmit results are returned for files with invalid metadata."""
        input_api = MockInputApi()
        input_api.change.RepositoryRoot = lambda: ''
        test_file = MockFile(os.path.normpath('foo/README.chromium'),
                             ['Shipped: yes?'])
        input_api.files = [test_file]
        results = presubmit_canned_checks.CheckChromiumDependencyMetadata(
            input_api, MockOutputApi())

        # There should be 9 results due to
        # - missing 5 mandatory fields: Name, URL, Version, License, and
        #                               Security Critical
        # - 1 error for insufficent versioning info
        # - missing 2 required fields: License File, and
        #                              License Android Compatible
        # - Shipped should be only 'yes' or 'no'.
        self.assertEqual(len(results), 9)

        # Check each presubmit result is associated with the test file.
        for result in results:
            self.assertEqual(len(result.items), 1)
            self.assertEqual(result.items[0], test_file)


class CheckUpdateOwnersFileReferences(unittest.TestCase):
    def testShowsWarningIfDeleting(self):
        input_api = MockInputApi()
        input_api.files = [
            MockFile(os.path.normpath('foo/OWNERS'), [], [], action='D'),
        ]
        results = presubmit_canned_checks.CheckUpdateOwnersFileReferences(
            input_api, MockOutputApi())
        self.assertEqual(1, len(results))
        self.assertEqual('warning', results[0].type)
        self.assertEqual(1, len(results[0].items))

    def testShowsWarningIfMoving(self):
        input_api = MockInputApi()
        input_api.files = [
            MockFile(os.path.normpath('new_directory/OWNERS'), [], [],
                     action='A'),
            MockFile(os.path.normpath('old_directory/OWNERS'), [], [],
                     action='D'),
        ]
        results = presubmit_canned_checks.CheckUpdateOwnersFileReferences(
            input_api, MockOutputApi())
        self.assertEqual(1, len(results))
        self.assertEqual('warning', results[0].type)
        self.assertEqual(1, len(results[0].items))

    def testNoWarningIfAdding(self):
        input_api = MockInputApi()
        input_api.files = [
            MockFile(os.path.normpath('foo/OWNERS'), [], [], action='A'),
        ]
        results = presubmit_canned_checks.CheckUpdateOwnersFileReferences(
            input_api, MockOutputApi())
        self.assertEqual(0, len(results))


class CheckNoNewGitFilesAddedInDependenciesTest(unittest.TestCase):

    @mock.patch('presubmit_canned_checks._readDeps')
    def testNonNested(self, readDeps):
        readDeps.return_value = '''deps = {
      'src/foo': {'url': 'bar', 'condition': 'non_git_source'},
      'src/components/foo/bar': {'url': 'bar', 'condition': 'non_git_source'},
    }'''

        input_api = MockInputApi()
        input_api.files = [
            MockFile('components/foo/file1.java', ['otherFunction']),
            MockFile('components/foo/file2.java', ['hasSyncConsent']),
            MockFile('chrome/foo/file3.java', ['canSyncFeatureStart']),
            MockFile('chrome/foo/file4.java', ['isSyncFeatureEnabled']),
            MockFile('chrome/foo/file5.java', ['isSyncFeatureActive']),
        ]
        results = presubmit_canned_checks.CheckNoNewGitFilesAddedInDependencies(
            input_api, MockOutputApi())

        self.assertEqual(0, len(results))

    @mock.patch('presubmit_canned_checks._readDeps')
    def testCollision(self, readDeps):
        readDeps.return_value = '''deps = {
      'src/foo': {'url': 'bar', 'condition': 'non_git_source'},
      'src/baz': {'url': 'baz'},
    }'''

        input_api = MockInputApi()
        input_api.files = [
            MockAffectedFile('fo', 'content'),  # no conflict
            MockAffectedFile('foo', 'content'),  # conflict
            MockAffectedFile('foo/bar', 'content'),  # conflict
            MockAffectedFile('baz/qux', 'content'),  # conflict, but ignored
        ]
        results = presubmit_canned_checks.CheckNoNewGitFilesAddedInDependencies(
            input_api, MockOutputApi())

        self.assertEqual(2, len(results))
        self.assertIn('File: foo', str(results))
        self.assertIn('File: foo/bar', str(results))

    @mock.patch('presubmit_canned_checks._readDeps')
    def testNoDeps(self, readDeps):
        readDeps.return_value = ''  # Empty deps

        input_api = MockInputApi()
        input_api.files = [
            MockAffectedFile('fo', 'content'),  # no conflict
            MockAffectedFile('foo', 'content'),  # conflict
            MockAffectedFile('foo/bar', 'content'),  # conflict
            MockAffectedFile('baz/qux', 'content'),  # conflict, but ignored
        ]
        results = presubmit_canned_checks.CheckNoNewGitFilesAddedInDependencies(
            input_api, MockOutputApi())

        self.assertEqual(0, len(results))


class CheckNewDEPSHooksHasRequiredReviewersTest(unittest.TestCase):

    def setUp(self):
        self.input_api = MockInputApi()
        self.input_api.change = MockChange([], issue=123)
        self.input_api.change.RepositoryRoot = lambda: ''

    def test_no_gerrit_cl(self):
        self.input_api.change = MockChange([], issue=None)
        results = presubmit_canned_checks.CheckNewDEPSHooksHasRequiredReviewers(
            self.input_api, MockOutputApi())
        self.assertEqual(0, len(results))

    def test_no_deps_file_change(self):
        self.input_api.files = [
            MockAffectedFile('foo.py', 'content'),
        ]
        results = presubmit_canned_checks.CheckNewDEPSHooksHasRequiredReviewers(
            self.input_api, MockOutputApi())
        self.assertEqual(0, len(results))

    def test_new_deps_hook(self):
        gerrit_mock = mock.Mock()
        self.input_api.gerrit = gerrit_mock
        test_cases = [
            {
                'name': 'no new hooks',
                'old_contents': ['hooks = []'],
                'new_contents': ['hooks = []'],
                'reviewers': [],
            },
            {
                'name':
                'add new hook and require review',
                'old_contents': ['hooks = [{"name": "old_hook"}]'],
                'new_contents': [
                    'hooks = [{"name": "old_hook"}, {"name": "new_hook"},  {"name": "new_hook_2"}]'
                ],
                'reviewers': [],
                'expected_error_msg':
                'New DEPS hooks (new_hook, new_hook_2) are found. Please '
                'request review from one of the following reviewers:\n '
                '* foo@chromium.org\n * bar@chromium.org\n * baz@chromium.org'
            },
            {
                'name':
                'add new hook and require approval',
                'old_contents': ['hooks = [{"name": "old_hook"}]'],
                'new_contents': [
                    'hooks = [{"name": "old_hook"}, {"name": "new_hook"},  {"name": "new_hook_2"}]'
                ],
                'submitting':
                True,
                'reviewers': ['not_relevant@chromium.org'],
                'expected_error_msg':
                'New DEPS hooks (new_hook, new_hook_2) are found. The CL must '
                'be approved by one of the following reviewers:\n'
                ' * foo@chromium.org\n * bar@chromium.org\n * baz@chromium.org'
            },
            {
                'name':
                'add new hook and reviewer is already added',
                'old_contents': ['hooks = [{"name": "old_hook"}]'],
                'new_contents': [
                    'hooks = [{"name": "old_hook"}, {"name": "new_hook"},  {"name": "new_hook_2"}]'
                ],
                'reviewers': ['baz@chromium.org'],
            },
            {
                'name':
                'add new hook and reviewer already approves',
                'old_contents': ['hooks = [{"name": "old_hook"}]'],
                'new_contents': [
                    'hooks = [{"name": "old_hook"}, {"name": "new_hook"},  {"name": "new_hook_2"}]'
                ],
                'submitting':
                True,
                'reviewers': ['foo@chromium.org'],
            },
            {
                'name':
                'change existing hook',
                'old_contents': [
                    'hooks = [{"name": "existing_hook", "action": ["run", "./test.sh"]}]'
                ],
                'new_contents': [
                    'hooks = [{"name": "existing_hook", "action": ["run", "./test_v2.sh"]}]'
                ],
                'reviewers': [],
            },
            {
                'name':
                'remove hook',
                'old_contents':
                ['hooks = [{"name": "old_hook"}, {"name": "hook_to_remove"}]'],
                'new_contents': ['hooks = [{"name": "old_hook"}]'],
                'reviewers': [],
            },
        ]
        for case in test_cases:
            with self.subTest(case_name=case['name']):
                self.input_api.files = [
                    MockFile('OWNERS', [
                        'per-file DEPS=foo@chromium.org # For new DEPS hook',
                        'per-file DEPS=bar@chromium.org, baz@chromium.org # For new DEPS hook'
                    ]),
                    MockAffectedFile('DEPS',
                                     old_contents=case['old_contents'],
                                     new_contents=case['new_contents']),
                ]
                if case.get('submitting', False):
                    self.input_api.is_committing = True
                    self.input_api.dry_run = False
                gerrit_mock.GetChangeReviewers.return_value = case['reviewers']
                results = presubmit_canned_checks.CheckNewDEPSHooksHasRequiredReviewers(
                    self.input_api,
                    MockOutputApi(),
                )
                if 'expected_error_msg' in case:
                    self.assertEqual(1, len(results))
                    self.assertEqual(case['expected_error_msg'],
                                     results[0].message)
                else:
                    self.assertEqual(0, len(results))


class CheckAyeAyeTest(unittest.TestCase):

    def setUp(self):
        super(CheckAyeAyeTest, self).setUp()
        self.addCleanup(mock.patch.stopall)

        self.input_api = MockInputApi()
        self.output_api = MockOutputApi()

        self.mock_repo_root = mock.patch.object(self.input_api.change,
                                                'RepositoryRoot',
                                                create=True).start()
        self.mock_repo_root.return_value = '/fake/repo/root'

        self.mock_popen = mock.patch.object(self.input_api.subprocess,
                                            'Popen',
                                            autospec=True).start()
        self.mock_proc = mock.Mock()
        self.mock_popen.return_value = self.mock_proc
        self.input_api.subprocess.PIPE = subprocess.PIPE
        self.input_api.subprocess.STDOUT = subprocess.STDOUT

        self.mock_exists = mock.patch.object(presubmit_canned_checks._os.path,
                                             'exists',
                                             autospec=True).start()
        self.mock_exists.return_value = True

    def test_ayeaye_findings(self):
        # Simulate alint output with color codes
        alint_output = (
            "\x1b[31mERROR:\x1b[0m This is an error.\n"
            "Some other info line\n"
            "\x1b[33mWARNING:\x1b[0m This is a warning.\n"
            "\x1b[94mINFO:\x1b[0m This is an info.\n"
            "\x1b[31mERROR:\x1b[0m Another error.\n"
            "\x1b[33mWARNING:\x1b[0m Another warning.").encode('utf-8')
        self.mock_proc.communicate.return_value = (alint_output, b'')
        self.mock_proc.returncode = 0

        results = presubmit_canned_checks.CheckAyeAye(self.input_api,
                                                      self.output_api)

        self.assertEqual(len(results), 4)

        result_types = sorted([r.type for r in results])
        self.assertEqual(result_types, ['error', 'error', 'warning', 'warning'])

        messages = sorted([r.message for r in results])
        expected_messages = sorted([
            "This is an error.",
            "Another error.",
            "This is a warning.",
            "Another warning.",
        ])
        self.assertEqual(messages, expected_messages)

        self.mock_popen.assert_called_once_with(
            ['/google/bin/releases/alint/alint', '--', '-t=9s'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd='/fake/repo/root')

    def test_ayeaye_no_findings(self):
        self.mock_proc.communicate.return_value = (
            b"\x1b[94mINFO:\x1b[0m All good", b'')
        self.mock_proc.returncode = 0
        results = presubmit_canned_checks.CheckAyeAye(self.input_api,
                                                      self.output_api)
        self.assertEqual(len(results), 0)

    def test_ayeaye_alint_not_found(self):
        self.mock_exists.return_value = False
        results = presubmit_canned_checks.CheckAyeAye(self.input_api,
                                                      self.output_api)
        self.assertEqual(len(results), 0)

    def test_ayeaye_subprocess_exception(self):
        self.mock_popen.side_effect = Exception("BOOM")
        results = presubmit_canned_checks.CheckAyeAye(self.input_api,
                                                      self.output_api)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].type, 'error')
        # Exact message depends on Exception type, so check for key parts
        self.assertIn("Unexpected error in CheckAyeAye:", results[0].message)
        self.assertIn("BOOM", results[0].message)

    def test_ayeaye_alint_fails(self):
        alint_output = (
            "\x1b[31mERROR:\x1b[0m Failed to run.\n").encode('utf-8')
        self.mock_proc.communicate.return_value = (alint_output, b'')
        self.mock_proc.returncode = 1  # Non-zero return code
        results = presubmit_canned_checks.CheckAyeAye(self.input_api,
                                                      self.output_api)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].type, 'error')
        self.assertIn("Failed to run.", results[0].message)


class CheckForCommitObjectsTest(unittest.TestCase):

    def setUp(self):
        self.input_api = MockInputApi()
        self.input_api.change.scm = 'git'
        self.input_api.subprocess = mock.Mock()
        self.output_api = MockOutputApi()

        self.patcher = mock.patch('presubmit_canned_checks._ParseDeps')
        self.mock_parse_deps = self.patcher.start()
        self.mock_parse_deps.return_value = {'git_dependencies': 'DEPS'}
        self.input_api.change.RepositoryRoot = lambda: ''

    def tearDown(self):
        self.patcher.stop()

    def testNoGitlinks(self):
        # No gitlinks at all.
        self.input_api.subprocess.check_output.side_effect = [
            b'',  # git show HEAD:DEPS
            b'100644 blob 1234\tfile.txt\0'
        ]

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(0, len(results))

    def testGitlinkFound(self):
        # One gitlink found.
        self.input_api.subprocess.check_output.side_effect = [
            b'',  # git show HEAD:DEPS
            b'160000 commit 1234\tsubmodule\0'
        ]

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(1, len(results))
        self.assertEqual('submodule', results[0].items[0])

    def testGitlinkMiddle(self):
        # Gitlink in the middle of other files.
        self.input_api.subprocess.check_output.side_effect = [
            b'',  # git show HEAD:DEPS
            b'100644 blob 1111\tfile1\0'
            b'160000 commit 2222\tsubmodule\0'
            b'100644 blob 3333\tfile2\0'
        ]

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(1, len(results))
        self.assertEqual('submodule', results[0].items[0])

    def testGitlinkStart(self):
        # Gitlink at the very start.
        self.input_api.subprocess.check_output.side_effect = [
            b'',  # git show HEAD:DEPS
            b'160000 commit 2222\tsubmodule\0'
            b'100644 blob 3333\tfile2\0'
        ]

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(1, len(results))
        self.assertEqual('submodule', results[0].items[0])

    def testGitlinkEnd(self):
        # Gitlink at the very end.
        self.input_api.subprocess.check_output.side_effect = [
            b'',  # git show HEAD:DEPS
            b'100644 blob 3333\tfile2\0'
            b'160000 commit 2222\tsubmodule\0'
        ]

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(1, len(results))
        self.assertEqual('submodule', results[0].items[0])

    def testMultipleGitlinks(self):
        # Multiple gitlinks.
        self.input_api.subprocess.check_output.side_effect = [
            b'',  # git show HEAD:DEPS
            b'160000 commit 1111\tsub1\0'
            b'100644 blob 2222\tfile\0'
            b'160000 commit 3333\tsub2\0'
        ]

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(1, len(results))
        self.assertEqual(2, len(results[0].items))
        self.assertIn('sub1', results[0].items)
        self.assertIn('sub2', results[0].items)

    @mock.patch('configparser.ConfigParser')
    def testMultipleGitlinksWithSameHashSync(self, mock_config_parser):
        # Multiple gitlinks with same hash syncing via DEPS.
        self.mock_parse_deps.return_value = {
            'git_dependencies': 'SYNC',
            'deps': {
                'src/third_party/sub1': 'https://repo.git@1111',
                'src/third_party/sub2': 'https://repo.git@1111'
            }
        }
        self.input_api.subprocess.check_output.side_effect = [
            b'',  # git show HEAD:DEPS
            b'160000 commit 1111\tsrc/third_party/sub1\0'
            b'160000 commit 1111\tsrc/third_party/sub2\0'
        ]

        mock_instance = mock_config_parser.return_value
        mock_instance.items.return_value = [('submodule "sub1"', {
            'path': 'src/third_party/sub1'
        }), ('submodule "sub2"', {
            'path': 'src/third_party/sub2'
        })]

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)

        self.assertEqual(0, len(results))

    def testFalsePositiveText(self):
        # "160000" in filename but not mode.
        self.input_api.subprocess.check_output.side_effect = [
            b'',  # git show HEAD:DEPS
            b'100644 blob 1234\t160000_file.txt\0'
        ]

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(0, len(results))

    def testRunFromSubdir_SmallFiles_NoSubmodules(self):
        self.input_api.presubmit_local_path = os.path.join(ROOT_DIR, 'subdir')
        self.input_api.change.RepositoryRoot = lambda: ROOT_DIR
        self.input_api.files = [MockAffectedFile('foo.txt', 'content')]
        self.input_api.subprocess.check_output.return_value = b''

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(0, len(results))

    def testRunFromSubdir_SmallFiles_WithSubmodules(self):
        self.input_api.presubmit_local_path = os.path.join(ROOT_DIR, 'subdir')
        self.input_api.change.RepositoryRoot = lambda: ROOT_DIR
        self.input_api.files = [MockAffectedFile('foo.txt', 'content')]
        self.input_api.subprocess.check_output.return_value = b'160000 commit 1234\tsubmodule\0'

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(1, len(results))
        self.assertIn('submodule', results[0].items)

    def testRunFromSubdir_LargeFiles_NoSubmodules(self):
        self.input_api.presubmit_local_path = os.path.join(ROOT_DIR, 'subdir')
        self.input_api.change.RepositoryRoot = lambda: ROOT_DIR
        self.input_api.files = [
            MockAffectedFile(f'f{i}', '') for i in range(1001)
        ]
        self.input_api.subprocess.check_output.return_value = b''

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(0, len(results))

    def testRunFromSubdir_LargeFiles_WithSubmodules(self):
        self.input_api.presubmit_local_path = os.path.join(ROOT_DIR, 'subdir')
        self.input_api.change.RepositoryRoot = lambda: ROOT_DIR
        self.input_api.files = [
            MockAffectedFile(f'f{i}', '') for i in range(1001)
        ]
        self.input_api.subprocess.check_output.return_value = b'160000 commit 1234\tsubmodule\0'

        results = presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)
        self.assertEqual(1, len(results))
        self.assertIn('submodule', results[0].items)

    def testWindowsCommandLineLimit(self):
        # On Windows, if the command line is too long, we should fall back to a
        # recursive ls-tree.
        self.input_api.platform = 'win32'
        self.input_api.files = [
            MockAffectedFile('a' * 100, '') for i in range(350)
        ]
        self.input_api.subprocess.check_output.return_value = b''

        presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)

        # The first call is to `git show HEAD:DEPS`.
        # The second call is to `git ls-tree`.
        self.assertEqual(2, self.input_api.subprocess.check_output.call_count)
        ls_tree_cmd = self.input_api.subprocess.check_output.call_args_list[1][0][0]
        self.assertIn('-r', ls_tree_cmd)

    def testWindowsCommandLineNotTooLong(self):
        # On Windows, if the command line is not too long, we should pass the
        # file list.
        self.input_api.platform = 'win32'
        self.input_api.files = [
            MockAffectedFile('foo.txt', '')
        ]
        self.input_api.subprocess.check_output.return_value = b''

        presubmit_canned_checks.CheckForCommitObjects(
            self.input_api, self.output_api)

        # The first call is to `git show HEAD:DEPS`.
        # The second call is to `git ls-tree`.
        self.assertEqual(2, self.input_api.subprocess.check_output.call_count)
        ls_tree_cmd = self.input_api.subprocess.check_output.call_args_list[1][0][0]
        self.assertNotIn('-r', ls_tree_cmd)
        self.assertIn('--', ls_tree_cmd)
        self.assertIn('foo.txt', ls_tree_cmd)

    def testWindowsSpecialCharacters(self):
        # On Windows, if a file contains special characters like '&', we don't
        # need to fall back to a recursive ls-tree when using shell=False.
        self.input_api.platform = 'win32'
        self.input_api.files = [MockAffectedFile('foo&bar.txt', '')]
        self.input_api.subprocess.check_output.return_value = b''

        presubmit_canned_checks.CheckForCommitObjects(self.input_api,
                                                      self.output_api)

        # The first call is to `git show HEAD:DEPS`.
        # The second call is to `git ls-tree`.
        self.assertEqual(2, self.input_api.subprocess.check_output.call_count)
        ls_tree_cmd = self.input_api.subprocess.check_output.call_args_list[1][
            0][0]
        self.assertNotIn('-r', ls_tree_cmd)
        self.assertIn('foo&bar.txt', ls_tree_cmd)


if __name__ == '__main__':
    unittest.main()

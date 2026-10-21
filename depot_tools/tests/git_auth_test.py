#!/usr/bin/env vpython3
# coding=utf-8
# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unit tests for git_cl.py."""

from __future__ import annotations

from collections.abc import Iterable
import io
import logging
import os
import sys
import tempfile
from typing import Iterable
import unittest
from unittest import mock
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import git_auth
import scm
import scm_mock


class TestParseCookiefile(unittest.TestCase):

    def test_ignore_comments(self):
        f = io.StringIO('''\
# chromium.googlesource.com,FALSE,/,TRUE,2147483647,o,git-ayatane.google.com=1//fake-credential
''')
        got = git_auth._parse_cookiefile(f)
        want = git_auth._CookiefileInfo(
            contains_gerrit=False,
            contains_nongerrit=False,
        )
        self.assertEqual(got, want)

    def test_gerrit(self):
        f = io.StringIO('''\
chromium.googlesource.com,FALSE,/,TRUE,2147483647,o,git-ayatane.google.com=1//fake-credential
''')
        got = git_auth._parse_cookiefile(f)
        want = git_auth._CookiefileInfo(
            contains_gerrit=True,
            contains_nongerrit=False,
        )
        self.assertEqual(got, want)

    def test_nongerrit(self):
        f = io.StringIO('''\
github.com,FALSE,/,TRUE,2147483647,o,git-ayatane.google.com=1//fake-credential
''')
        got = git_auth._parse_cookiefile(f)
        want = git_auth._CookiefileInfo(
            contains_gerrit=False,
            contains_nongerrit=True,
        )
        self.assertEqual(got, want)

    def test_both(self):
        f = io.StringIO('''\
chromium.googlesource.com,FALSE,/,TRUE,2147483647,o,git-ayatane.google.com=1//fake-credential
github.com,FALSE,/,TRUE,2147483647,o,git-ayatane.google.com=1//fake-credential
''')
        got = git_auth._parse_cookiefile(f)
        want = git_auth._CookiefileInfo(
            contains_gerrit=True,
            contains_nongerrit=True,
        )
        self.assertEqual(got, want)


class TestConfigWizard(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        super().setUp()
        self._global_state_view: Iterable[tuple[str,
                                                list[str]]] = scm_mock.GIT(self)
        self.ui = _FakeUI()

        self.wizard = git_auth.ConfigWizard(
            ui=self.ui, remote_url_func=lambda: 'remote.example.com')

    @property
    def global_state(self):
        return dict(self._global_state_view)

    def test_configure_sso_global(self):
        parts = urllib.parse.urlsplit(
            'https://chromium.googlesource.com/chromium/tools/depot_tools.git')
        self.wizard._configure_sso(parts, scope='global')
        want = {
            'url.sso://chromium/.insteadof': [
                'https://chromium.googlesource.com/',
                'https://chromium-review.googlesource.com/'
            ],
        }
        self.assertEqual(self.global_state, want)

    def test_configure_sso_global_with_review_host(self):
        parts = urllib.parse.urlsplit(
            'https://chromium-review.googlesource.com/chromium/tools/depot_tools.git'
        )
        self.wizard._configure_sso(parts, scope='global')
        want = {
            'url.sso://chromium/.insteadof': [
                'https://chromium.googlesource.com/',
                'https://chromium-review.googlesource.com/'
            ],
        }
        self.assertEqual(self.global_state, want)

    def test_configure_oauth_global(self):
        parts = urllib.parse.urlsplit(
            'https://chromium.googlesource.com/chromium/tools/depot_tools.git')
        self.wizard._configure_oauth(parts, scope='global')
        want = {
            'credential.https://chromium.googlesource.com.helper': ['', 'luci'],
            'credential.https://chromium.googlesource.com.usehttppath': ['yes'],
        }
        self.assertEqual(self.global_state, want)

    def test_configure_oauth_global_with_review_host(self):
        parts = urllib.parse.urlsplit(
            'https://chromium-review.googlesource.com/chromium/tools/depot_tools.git'
        )
        self.wizard._configure_oauth(parts, scope='global')
        want = {
            'credential.https://chromium-review.googlesource.com.helper':
            ['', 'luci'],
            'credential.https://chromium-review.googlesource.com.usehttppath':
            ['yes'],
        }
        self.assertEqual(self.global_state, want)

    def test_configure_sso_global_oauth_local(self):
        parts = urllib.parse.urlsplit(
            'https://chromium.googlesource.com/chromium/tools/depot_tools.git')
        self.wizard._configure_sso(parts, scope='global')
        want = {
            'url.sso://chromium/.insteadof': [
                'https://chromium.googlesource.com/',
                'https://chromium-review.googlesource.com/'
            ],
        }
        self.assertEqual(self.global_state, want)
        self.wizard._configure_oauth(parts, scope='local')
        self.assertEqual(
            scm.GIT.GetConfigList(
                os.getcwd(),
                'credential.https://chromium.googlesource.com.helper'),
            ['', 'luci'])
        # Ensure that we're overriding the global overwrite rule
        self.assertEqual(
            scm.GIT.GetConfigList(
                os.getcwd(),
                'url.https://chromium.googlesource.com/chromium/tools/depot_tools.git.insteadof'
            ), [
                'https://chromium.googlesource.com/chromium/tools/depot_tools.git',
            ])

    def test_configure_review_sso_global_oauth_local(self):
        parts = urllib.parse.urlsplit(
            'https://chromium-review.googlesource.com/chromium/tools/depot_tools.git'
        )
        self.wizard._configure_sso(parts, scope='global')
        want = {
            'url.sso://chromium/.insteadof': [
                'https://chromium.googlesource.com/',
                'https://chromium-review.googlesource.com/'
            ],
        }
        self.assertEqual(self.global_state, want)
        self.wizard._configure_oauth(parts, scope='local')
        self.assertEqual(
            scm.GIT.GetConfigList(
                os.getcwd(),
                'credential.https://chromium-review.googlesource.com.helper'),
            ['', 'luci'])
        # Ensure that we're overriding the global overwrite rule
        self.assertEqual(
            scm.GIT.GetConfigList(
                os.getcwd(),
                'url.https://chromium-review.googlesource.com/chromium/tools/depot_tools.git.insteadof'
            ), [
                'https://chromium-review.googlesource.com/chromium/tools/depot_tools.git',
            ])

    @mock.patch('git_auth.ConfigWizard._check_use_sso', spec=True)
    def test_configure_host_clears_conflicting_local_stale(self, check):
        parts = urllib.parse.urlsplit(
            'https://chromium.googlesource.com/chromium/tools/depot_tools.git')
        email = 'columbina@example.com'

        check.return_value = True
        self.wizard._configure_host(parts, email, scope='local')
        # Check local rule is created
        self.assertEqual(
            scm.GIT.GetConfigList(os.getcwd(), 'url.sso://chromium/.insteadof'),
            [
                'https://chromium.googlesource.com/',
                'https://chromium-review.googlesource.com/',
            ])

        check.return_value = False
        self.wizard._configure_host(parts, email, scope='global')
        want = {
            'credential.https://chromium.googlesource.com.helper': ['', 'luci'],
            'credential.https://chromium.googlesource.com.usehttppath': ['yes'],
        }
        self.assertEqual(self.global_state, want)
        # Ensure the local rule gets purged
        self.assertEqual(
            scm.GIT.GetConfigList(os.getcwd(), 'url.sso://chromium/.insteadof'),
            [])

    @mock.patch('git_auth.ConfigWizard._check_use_sso', spec=True)
    def test_configure_host_outside_repo_keeps_local_stale(self, check):
        parts = urllib.parse.urlsplit(
            'https://chromium.googlesource.com/chromium/tools/depot_tools.git')
        email = 'columbina@example.com'

        check.return_value = True
        self.wizard._configure_host(parts, email, scope='local')
        # Check local rule is created
        self.assertEqual(
            scm.GIT.GetConfigList(os.getcwd(), 'url.sso://chromium/.insteadof'),
            [
                'https://chromium.googlesource.com/',
                'https://chromium-review.googlesource.com/',
            ])

        check.return_value = False
        wizard = git_auth.ConfigWizard(ui=self.ui, remote_url_func=lambda: '')
        wizard._configure_host(parts, email, scope='global')
        want = {
            'credential.https://chromium.googlesource.com.helper': ['', 'luci'],
            'credential.https://chromium.googlesource.com.usehttppath': ['yes'],
        }
        self.assertEqual(self.global_state, want)
        # Check the local rule remains.
        # This test is wonky because the scm.GIT mock always assumes we're in a repo
        self.assertEqual(
            scm.GIT.GetConfigList(os.getcwd(), 'url.sso://chromium/.insteadof'),
            [
                'https://chromium.googlesource.com/',
                'https://chromium-review.googlesource.com/',
            ])


    def test_check_gitcookies_same(self):
        with tempfile.NamedTemporaryFile() as gitcookies:
            self.wizard._gitcookies = lambda: gitcookies.name
            scm.GIT.SetConfig(os.getcwd(),
                              'http.cookiefile',
                              gitcookies.name,
                              scope='global')
            got = self.wizard._check_gitcookies()
            want = git_auth._GitcookiesSituation(
                gitcookies_exists=True,
                cookiefile=gitcookies.name,
                cookiefile_exists=True,
                divergent_cookiefiles=False,
            )
            self.assertEqual(got, want)

    def test_check_gitcookies_different(self):
        with tempfile.NamedTemporaryFile(
        ) as gitcookies, tempfile.NamedTemporaryFile() as cookiefile:
            self.wizard._gitcookies = lambda: gitcookies.name
            scm.GIT.SetConfig(os.getcwd(),
                              'http.cookiefile',
                              cookiefile.name,
                              scope='global')
            got = self.wizard._check_gitcookies()
            want = git_auth._GitcookiesSituation(
                gitcookies_exists=True,
                cookiefile=cookiefile.name,
                cookiefile_exists=True,
                divergent_cookiefiles=True,
            )
            self.assertEqual(got, want)

    def test_check_gitcookies_missing_gitcookies(self):
        with tempfile.NamedTemporaryFile() as cookiefile:
            self.wizard._gitcookies = lambda: '/this-file-does-not-exist-yue'
            scm.GIT.SetConfig(os.getcwd(),
                              'http.cookiefile',
                              cookiefile.name,
                              scope='global')
            got = self.wizard._check_gitcookies()
            want = git_auth._GitcookiesSituation(
                gitcookies_exists=False,
                cookiefile=cookiefile.name,
                cookiefile_exists=True,
                divergent_cookiefiles=False,
            )
            self.assertEqual(got, want)

    def test_check_gitcookies_missing_cookiefile(self):
        with tempfile.NamedTemporaryFile() as gitcookies:
            self.wizard._gitcookies = lambda: gitcookies.name
            scm.GIT.SetConfig(os.getcwd(),
                              'http.cookiefile',
                              '/this-file-does-not-exist-yue',
                              scope='global')
            got = self.wizard._check_gitcookies()
            want = git_auth._GitcookiesSituation(
                gitcookies_exists=True,
                cookiefile='/this-file-does-not-exist-yue',
                cookiefile_exists=False,
                divergent_cookiefiles=False,
            )
            self.assertEqual(got, want)

    def test_check_gitcookies_unset(self):
        with tempfile.NamedTemporaryFile() as gitcookies:
            self.wizard._gitcookies = lambda: gitcookies.name
            got = self.wizard._check_gitcookies()
            want = git_auth._GitcookiesSituation(
                gitcookies_exists=True,
                cookiefile='',
                cookiefile_exists=False,
                divergent_cookiefiles=False,
            )
            self.assertEqual(got, want)

    def test_move_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'foo')
            open(path, 'w').close()
            self.wizard._move_file(path)
            self.assertEqual(os.listdir(d), ['foo.bak'])

    def test_move_file_backup_exists(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'foo')
            open(path, 'w').close()
            open(os.path.join(d, 'foo.bak'), 'w').close()
            self.wizard._move_file(path)
            self.assertEqual(sorted(os.listdir(d)), ['foo.bak', 'foo.bak2'])


class _FakeUI(object):
    """Implements UserInterface for testing."""

    def __init__(self, choices: Iterable[str] = ()):
        self.choices: list[str] = list(choices)

    def read_yn(self, prompt: str, *, default: bool | None = None) -> bool:
        choice = self.choices.pop(0)
        if choice == 'y':
            return True
        if choice == 'n':
            return False
        raise Exception(f'invalid choice for yn {choice!r}')

    def read_line(self, prompt: str, *, check=lambda *any: True) -> str:
        return self.choices.pop(0)

    def write(self, s: str) -> None:
        pass


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG if '-v' in sys.argv else logging.ERROR)
    unittest.main()

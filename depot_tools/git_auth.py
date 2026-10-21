# Copyright (c) 2024 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Defines utilities for setting up Git authentication."""

from __future__ import annotations

import enum
from collections.abc import Collection
import contextlib
import functools
import logging
import os
from typing import Callable, Iterable, NamedTuple, TextIO
import urllib.parse

import gerrit_util
import newauth
import scm


class _ConfigError(Exception):
    """Subclass for errors raised by ConfigWizard.

    This may be unused, but keep this around so that anyone who needs it
    when tweaking ConfigWizard can use it.
    """


class _ConfigMethod(enum.Enum):
    """Enum used in _ConfigInfo."""
    OAUTH = 1
    SSO = 2


class _ConfigInfo(NamedTuple):
    """Result for ConfigWizard._configure."""
    method: _ConfigMethod


class _GitcookiesSituation(NamedTuple):
    """Result for ConfigWizard._check_gitcookies."""
    gitcookies_exists: bool
    cookiefile: str
    cookiefile_exists: bool
    divergent_cookiefiles: bool


_InputChecker = Callable[['UserInterface', str], bool]


def _check_any(ui: UserInterface, line: str) -> bool:
    """Allow any input."""
    return True


def _check_nonempty(ui: UserInterface, line: str) -> bool:
    """Reject nonempty input."""
    if line:
        return True
    ui.write('Input cannot be empty.\n')
    return False


def _check_choice(choices: Collection[str]) -> _InputChecker:
    """Allow specified choices."""

    def func(ui: UserInterface, line: str) -> bool:
        if line in choices:
            return True
        ui.write('Invalid choice.\n')
        return False

    return func


class UserInterface(object):
    """Abstracts user interaction for ConfigWizard.

    This implementation supports regular terminals.
    """

    _prompts = {
        None: 'y/n',
        True: 'Y/n',
        False: 'y/N',
    }

    def __init__(self, stdin: TextIO, stdout: TextIO):
        self._stdin = stdin
        self._stdout = stdout

    def read_yn(self, prompt: str, *, default: bool | None = None) -> bool:
        """Reads a yes/no response.

        The prompt should end in '?'.
        """
        prompt = f'{prompt} [{self._prompts[default]}]: '
        while True:
            self._stdout.write(prompt)
            self._stdout.flush()
            response = self._stdin.readline().strip().lower()
            if response in ('y', 'yes'):
                return True
            if response in ('n', 'no'):
                return False
            if not response and default is not None:
                return default
            self._stdout.write('Type y or n.\n')

    def read_line(self,
                  prompt: str,
                  *,
                  check: _InputChecker = _check_any) -> str:
        """Reads a line of input.

        Trailing whitespace is stripped from the read string.
        The prompt should not end in any special indicator like a colon.

        Optionally, an input check function may be provided.  This
        method will continue to prompt for input until it passes the
        check.  The check should print some explanation for rejected
        inputs.
        """
        while True:
            self._stdout.write(f'{prompt}: ')
            self._stdout.flush()
            s = self._stdin.readline().rstrip()
            if check(self, s):
                return s

    def read_enter(self, text: str = 'Press Enter to proceed.') -> None:
        """Reads an Enter.

        Used to interactively proceed.
        """
        self._stdout.write(text)
        self._stdout.flush()
        self._stdin.readline()

    def write(self, s: str) -> None:
        """Write string as-is.

        The string should usually end in a newline.
        """
        self._stdout.write(s)


RemoteURLFunc = Callable[[], str]


class ConfigWizard(object):
    """Wizard for setting up user's Git config Gerrit authentication.

    Instances carry internal state, so cannot be reused.
    """

    def __init__(self, *, ui: UserInterface, remote_url_func: RemoteURLFunc):
        self._ui = ui
        self._remote_url_func = remote_url_func

        # Internal state
        self._user_actions = []

    def run(self, *, force_global: bool) -> None:
        with self._handle_config_errors():
            self._run(force_global=force_global)

    def _run(self, *, force_global: bool) -> None:
        self._println('This tool will help check your Gerrit authentication.')
        self._println(
            '(Report any issues to https://issues.chromium.org/issues/new?component=1456702&template=2076315)'
        )
        self._println()
        self._fix_netrc()
        self._fix_gitcookies()
        self._println()
        self._println('Checking for SSO helper...')
        if self._check_sso_helper():
            self._println('SSO helper is available.')
            self._set_config('protocol.sso.allow', 'always', scope='global')
        self._check_gce()
        self._println()
        self._run_gerrit_host_configuration(force_global=force_global)
        self._println()
        self._println('Successfully finished auth configuration check.')
        self._print_actions_for_user()

    def _run_gerrit_host_configuration(self, *, force_global: bool) -> None:
        if force_global:
            self._println(
                'Since you passed --global, we will check your global Git configuration.'
            )
            self._run_outside_repo()
            return
        remote_url = self._remote_url_func()
        if _is_gerrit_url(remote_url):
            self._println(
                'Looks like we are running inside a Gerrit repository,')
            self._println('so we will check your Git configuration for it.')
            self._run_inside_repo()
        else:
            self._println(
                'Looks like we are running outside of a Gerrit repository,')
            self._println('so we will check your global Git configuration.')
            self._run_outside_repo()

    def _run_outside_repo(self) -> None:
        global_email = self._check_global_email()

        self._println()
        self._println('Since we are not running in a Gerrit repository,')
        self._println('we do not know which Gerrit host to check.')
        self._println(
            'You can re-run this command inside a Gerrit repository to check a specific host,'
        )
        self._println('or we can set up some commonly used Gerrit hosts.')

        self._println()
        self._println(
            "(If you haven't already set up auth for these Gerrit hosts,")
        self._println(
            "and you skip this, then you won't be able to auth to those hosts.")
        self._println(
            "This means lots of things will fail, like gclient sync.)")

        self._println()
        if not self._read_yn('Set up commonly used Gerrit hosts?',
                             default=True):
            self._println('Okay, skipping Gerrit host setup.')
            self._println(
                'You can re-run this command later or follow the instructions for manual configuration.'
            )
            self._print_manual_instructions()
            return

        hosts = [
            'android.googlesource.com',
            'aomedia.googlesource.com',
            'beto-core.googlesource.com',
            'boringssl.googlesource.com',
            'chromium.googlesource.com',
            'chrome-internal.googlesource.com',
            'dawn.googlesource.com',
            'pdfium.googlesource.com',
            'quiche.googlesource.com',
            'skia.googlesource.com',
            'swiftshader.googlesource.com',
            'webrtc.googlesource.com',
        ]

        self._println()
        self._println('We will set up auth for the following hosts:')
        for host in hosts:
            self._println(f'- {host}')
        self._println()
        self._read_enter()

        used_oauth = False
        for host in hosts:
            self._println()
            self._println(f'Checking authentication config for {host}')
            parts = urllib.parse.urlsplit(f'https://{host}/')
            info = self._configure_host(parts, global_email, scope='global')
            if info.method == _ConfigMethod.OAUTH:
                used_oauth = True
        if used_oauth:
            self._print_oauth_instructions()

        self._println()
        self._println(
            "If you need to set up any uncommonly used hosts that we didn't set up above,"
        )
        self._println('you can set them up manually.')
        self._print_manual_instructions()

    def _run_inside_repo(self) -> None:
        global_email = self._check_global_email()
        info = self._configure_repo(global_email=global_email)
        # This repo should be confirmed to be Gerrit by this point.
        assert info is not None
        if info.method == _ConfigMethod.OAUTH:
            self._print_oauth_instructions()

        dirs = list(scm.GIT.ListSubmodules(os.getcwd()))
        if dirs:
            self._println()
            self._println('This repository appears to have submodules.')
            self._println(
                'These may use different Gerrit hosts and need to be configured separately.'
            )
            self._println_action(
                "If you haven't yet, run `git cl creds-check --global` to configure common Gerrit hosts."
            )

    # Configuring Git for Gerrit auth

    def _configure_repo(self, *, global_email: str) -> _ConfigInfo | None:
        """Configure current Git repo for Gerrit auth.

        Returns None if current Git repo doesn't have Gerrit remote.
        """
        self._println()
        self._println(f'Configuring Gerrit auth for {os.getcwd()}')

        remote_url = self._remote_url_func()
        if not _is_gerrit_url(remote_url):
            self._println(
                f"Current repo remote {remote_url} doesn't look like Gerrit, so skipping"
            )
            return None
        self._println(f"Repo remote is {remote_url}")

        local_email = self._check_local_email()
        if local_email and local_email != global_email:
            self._println()
            self._println(
                'You have different emails configured locally vs globally.')
            self._println(
                'We will configure Gerrit authentication for your local repo only.'
            )
            email = local_email
            scope = 'local'
        else:
            self._println(
                "Since you don't have a different local email, we'll set up auth in your global config"
            )
            self._println('alongside your globally configured email.')
            email = global_email
            scope = 'global'
        self._println()
        parts = urllib.parse.urlsplit(remote_url)
        return self._configure_host(parts, email, scope=scope)

    def _configure_host(self, parts: urllib.parse.SplitResult, email: str, *,
                        scope: scm.GitConfigScope) -> _ConfigInfo:
        """Configure auth for one Gerrit host."""
        use_sso = self._check_use_sso(parts, email)
        if use_sso:
            self._configure_sso(parts, scope=scope)
            return _ConfigInfo(method=_ConfigMethod.SSO)
        self._configure_oauth(parts, scope=scope)
        if scope == 'global':
            # Clear any potential overriding local config
            self._clear_local_host_config(parts)
        return _ConfigInfo(method=_ConfigMethod.OAUTH)

    def _configure_sso(self, parts: urllib.parse.SplitResult, *,
                       scope: scm.GitConfigScope) -> None:
        if parts.scheme == 'sso':
            self._println(f'Your remote URL {parts.geturl()} already uses SSO')
        else:
            self._set_sso_rewrite(parts, scope=scope)
        self._clear_url_rewrite_override(parts, scope=scope)

    def _configure_oauth(self, parts: urllib.parse.SplitResult, *,
                         scope: scm.GitConfigScope) -> None:
        self._set_oauth_helper(parts, scope=scope)
        if scope == 'local':
            # Override a potential SSO rewrite set in the global config
            self._set_url_rewrite_override(parts, scope=scope)
        self._clear_sso_rewrite(parts, scope=scope)

    def _clear_local_host_config(self, parts: urllib.parse.SplitResult):
        """Clear auth config for one Gerrit host.

        This is used to clear any local config that might override a
        correct global config, as we default to configuring the global
        config if the local config has the same email, but the local
        config might have stale settings.
        """
        # Skip this if we're not inside a Git repo.
        if not self._remote_url_func():
            return
        self._clear_url_rewrite_override(parts, scope='local')
        self._clear_sso_rewrite(parts, scope='local')

    # Fixing competing auth

    def _fix_netrc(self) -> None:
        # https://curl.se/libcurl/c/CURLOPT_NETRC_FILE.html
        netrc_paths = ['~/.netrc']
        if self._is_windows():
            netrc_paths.append('~/_netrc')

        for path in netrc_paths:
            path = os.path.expanduser(path)
            if os.path.exists(path):
                self._println(f'You have a netrc file {path!r}')
                if self._read_yn(
                        'Shall we move your netrc file (to a backup location)?',
                        default=True):
                    self._move_file(path)

    def _fix_gitcookies(self) -> None:
        sit = self._check_gitcookies()
        if not sit.cookiefile:
            self._println(
                "You don't have a cookie file configured in Git (good).")
            if sit.gitcookies_exists:
                self._println(
                    'However, you have a .gitcookies file (which is not configured for Git).'
                )
                self._println(
                    'This won"t affect Git authentication, but may cause issues for'
                )
                self._println('other Gerrit operations in depot_tools.')
                if self._read_yn(
                        'Shall we move your .gitcookies file (to a backup location)?',
                        default=True):
                    self._move_file(self._gitcookies())
                    self._println(
                        'Note that some tools may still use the (legacy) .gitcookies file.'
                    )
                    self._println(
                        'If you encounter an issue, please report it.')
            return

        self._println('You appear to have a cookie file configured for Git.')
        self._println(f'http.cookiefile={sit.cookiefile!r}')

        if not sit.cookiefile_exists:
            self._println('However, this file does not exist.')
            self._println(
                'This will not affect anything, but we suggest removing the http.cookiefile from your Git config.'
            )
            if self._read_yn('Shall we remove it for you?', default=True):
                self._set_config('http.cookiefile', None, scope='global')
            return

        if sit.divergent_cookiefiles:
            self._println()
            self._println(
                'You also have a .gitcookies file, which is different from the cookefile in your Git config.'
            )
            self._println('We cannot handle this unusual case right now.')
            raise _ConfigError('unusual gitcookie setup')

        with open(sit.cookiefile, 'r') as f:
            info = _parse_cookiefile(f)

        if not info.contains_gerrit:
            self._println(
                "The cookie file doesn't appear to contain any Gerrit cookies,")
            self._println('so we will ignore it.')
            return

        if info.contains_nongerrit:
            self._println(
                'The cookie file contains Gerrit cookies and non-Gerrit cookies.'
            )
            self._println(
                'Cookie auth is deprecated, and these cookies may interfere with Gerrit authentication.'
            )
            self._println(
                "Since you have non-Gerrit cookies too, we won't try to fix it for you."
            )
            self._println_action(
                f'Please remove the Gerrit cookies (lines containing .googlesource.com) from {sit.cookiefile}'
            )
            return

        self._println('The cookie file contains Gerrit cookies.')
        self._println(
            'Cookie auth is deprecated, and these cookies may interfere with Gerrit authentication.'
        )
        if not self._read_yn(
                'Shall we move your cookie file (to a backup location)?',
                default=True):
            self._println(
                'Okay, we recommend that you move (or remove) it later to avoid issues.'
            )
            return

        self._move_file(sit.cookiefile)
        self._set_config('http.cookiefile', None, scope='global')

    # Self-contained checks for specific things

    def _check_gitcookies(self) -> _GitcookiesSituation:
        """Checks various things about the user's gitcookies situation."""
        gitcookies = self._gitcookies()
        gitcookies_exists = os.path.exists(gitcookies)
        cookiefile = os.path.expanduser(
            scm.GIT.GetConfig(os.getcwd(), 'http.cookiefile', scope='global')
            or '')
        cookiefile_exists = os.path.exists(cookiefile)
        divergent_cookiefiles = gitcookies_exists and cookiefile_exists and not os.path.samefile(
            gitcookies, cookiefile)
        return _GitcookiesSituation(
            gitcookies_exists=gitcookies_exists,
            cookiefile=cookiefile,
            cookiefile_exists=cookiefile_exists,
            divergent_cookiefiles=divergent_cookiefiles,
        )

    def _check_gce(self):
        if not gerrit_util.GceAuthenticator.is_applicable():
            return
        self._println()
        self._println('This appears to be a GCE VM.')
        self._println('You will need to add `export SKIP_GCE_AUTH_FOR_GIT=1`')
        self._println('to your .bashrc or similar.')
        fallback_msg = 'Add `export SKIP_GCE_AUTH_FOR_GIT=1` to your .bashrc or similar.'
        if self._is_windows():
            # Can't automatically handle Windows yet.
            self._println_action(fallback_msg)
            return
        rcfile: str | None = None
        options = [
            os.path.expanduser('~/.bashrc'),
        ]

        for p in options:
            if os.path.exists(p):
                self._println(f'We found {p!r}')
                rcfile = p
                break
        if not rcfile:
            self._println("We couldn't automatically detect your rcfile")
            self._println("so you'll need to do it manually.")
            self._println_action(fallback_msg)
            return
        if self._read_yn(f'Shall we add this line to {rcfile}?', default=True):
            self._append_to_file(rcfile, 'export SKIP_GCE_AUTH_FOR_GIT=1')
            self._println_action(
                'Restart your shell/terminal to use the updated environment.')
            return
        self._println_action(fallback_msg)

    def _check_global_email(self) -> str:
        """Checks and returns user's global Git email.

        Prompts the user to set it if it isn't set.
        """
        email = scm.GIT.GetConfig(os.getcwd(), 'user.email',
                                  scope='global') or ''
        if email:
            self._println(f'Your global Git email is: {email}')
            return email
        self._println()
        self._println(
            'You do not have an email configured in your global Git config.')
        if not self._read_yn('Do you want to set one now?', default=True):
            self._println('Will attempt to continue without a global email.')
            return ''
        name = scm.GIT.GetConfig(os.getcwd(), 'user.name', scope='global') or ''
        if not name:
            name = self._read_line('Enter your name (e.g., John Doe)',
                                   check=_check_nonempty)
            self._set_config('user.name', name, scope='global')
        email = self._read_line('Enter your email', check=_check_nonempty)
        self._set_config('user.email', email, scope='global')
        return email

    def _check_local_email(self) -> str:
        """Checks and returns the user's local Git email."""
        email = scm.GIT.GetConfig(os.getcwd(), 'user.email',
                                  scope='local') or ''
        if email:
            self._println(
                f'You have an email configured in your local repo: {email}')
        return email

    def _check_use_sso(self, parts: urllib.parse.SplitResult,
                       email: str) -> bool:
        """Checks whether SSO is needed for the given user and host."""
        if not self._check_sso_helper():
            return False
        host = _url_review_host(parts)
        self._println(f'Checking SSO requirement for {email!r} on {host}')
        self._println(
            '(Note that this check may require SSO; if you get an error,')
        self._println('you will need to login to SSO and re-run this command.)')
        result = gerrit_util.CheckShouldUseSSO(host, email)
        text = 'use' if result.status else 'not use'
        self._println(f'Decided we should {text} SSO for {email!r} on {host}')
        self._println(f'Reason: {result.reason}')
        self._println()
        return result.status

    def _check_sso_helper(self) -> bool:
        """Checks and returns whether SSO helper is available."""
        return bool(gerrit_util.ssoHelper.find_cmd())

    # Reused instruction printing

    def _print_manual_instructions(self) -> None:
        """Prints manual instructions for setting up auth."""
        self._println()
        self._println(
            'Instructions for manually configuring Gerrit authentication:')
        self._println(
            'https://commondatastorage.googleapis.com/chrome-infra-docs/flat/depot_tools/docs/html/depot_tools_gerrit_auth.html'
        )

    def _print_oauth_instructions(self) -> None:
        """Prints instructions for setting up OAuth helper."""
        self._println()
        self._println('We have configured Git to use an OAuth helper.')
        self._println('The OAuth helper requires its own login.')
        self._println_action(
            "If you haven't yet, run `git credential-luci login` using the same email as Git."
        )
        self._println(
            "(If you have already done this, you don't need to do it again.)")
        self._println(
            '(However, if you changed your email, you should do this again')
        self._println("to ensure you're using the right account.)")

    # Low level Git config manipulation

    def _set_oauth_helper(self, parts: urllib.parse.SplitResult, *,
                          scope: scm.GitConfigScope) -> None:
        cred_key = f'credential.{_url_host_url(parts)}.helper'
        self._set_config(cred_key, '', modify_all=True, scope=scope)
        self._set_config(cred_key, 'luci', append=True, scope=scope)
        self._set_config(f'credential.{_url_host_url(parts)}.useHttpPath',
                         'yes',
                         modify_all=True,
                         scope=scope)

    def _set_sso_rewrite(self, parts: urllib.parse.SplitResult, *,
                         scope: scm.GitConfigScope) -> None:
        self._set_url_rewrites(
            _url_gerrit_sso_url(parts),
            [_url_git_root_url(parts),
             _url_review_root_url(parts)],
            scope=scope)

    def _clear_sso_rewrite(self, parts: urllib.parse.SplitResult, *,
                           scope: scm.GitConfigScope) -> None:
        self._set_url_rewrites(_url_gerrit_sso_url(parts), [], scope=scope)

    def _set_url_rewrite_override(self, parts: urllib.parse.SplitResult, *,
                                  scope: scm.GitConfigScope) -> None:
        """Set a URL rewrite config that rewrites a URL to itself.

        This is used to override a global rewrite rule.
        """
        self._set_url_rewrites(parts.geturl(), [parts.geturl()], scope=scope)

    def _clear_url_rewrite_override(self, parts: urllib.parse.SplitResult, *,
                                    scope: scm.GitConfigScope) -> None:
        self._set_url_rewrites(parts.geturl(), [], scope=scope)

    def _set_url_rewrites(self, new: str, old: Iterable[str], *,
                          scope: scm.GitConfigScope) -> None:
        """Set URL rewrite config.

        Because Git URL rewrites are set as `new -> multiple old`, we
        should set all of them together.

        This should be called at most once per wizard invocation per
        url_key.
        """
        self._set_config(f'url.{new}.insteadOf',
                         None,
                         scope=scope,
                         modify_all=True)
        for url in old:
            self._set_config(f'url.{new}.insteadOf',
                             url,
                             append=True,
                             scope=scope)

    def _set_config(self,
                    key: str,
                    value: str | None,
                    *,
                    scope: scm.GitConfigScope,
                    modify_all: bool = False,
                    append: bool = False) -> None:
        """Set a Git config option."""
        scope_msg = f'In your {scope} Git config,'
        if append:
            assert value is not None
            self._println_notify(
                f'{scope_msg} we appended {key}={value!r} to existing values')
        else:
            if value is None:
                action = f"we cleared {'all values' if modify_all else 'the value'} for {key}"
            else:
                action = f'we set {key}={value!r}'
                if modify_all:
                    action += ', replacing any existing values'
            self._println_notify(f'{scope_msg} {action}')

        scm.GIT.SetConfig(os.getcwd(),
                          key,
                          value,
                          scope=scope,
                          modify_all=modify_all,
                          append=append)

    # Low level misc helpers

    def _append_to_file(self, path: str, line: str) -> None:
        """Append line to file.

        One newline is written before and after the given line string.
        """
        with open(path, 'a') as f:
            f.write('\n')
            f.write(line)
            f.write('\n')
        self._println_notify(f'Added {line!r} to {path!r}')

    def _move_file(self, path: str) -> None:
        """Move file to a backup path."""
        backup = f'{path}.bak'
        n = 1
        while os.path.exists(backup):
            n += 1
            backup = f'{path}.bak{n}'
        os.rename(path, backup)
        self._println_notify(f'Moved {path!r} to {backup!r}')

    @contextlib.contextmanager
    def _handle_config_errors(self):
        try:
            yield None
        except _ConfigError as e:
            self._println(f'ConfigError: {e!s}')

    def _print_actions_for_user(self) -> None:
        """Print manual actions requested from user.

        Aggregates any actions printed throughout the wizard run so it's
        easier for the user.
        """
        if not self._user_actions:
            return
        self._println()
        self._println(
            "However, there are some manual actions that are suggested")
        self._println("(you don't have to re-run this command afterward):")
        for s in self._user_actions:
            self._println(f'- {s}')

    def _println_action(self, s: str) -> None:
        """Print a notification about a manual action request from user.

        Also queues up the action for _print_actions_for_user.
        """
        self._println(f'!!! {s}')
        self._user_actions.append(s)

    def _println_notify(self, s: str) -> None:
        """Print a notification about a change we made."""
        self._println(f'>>> {s}')

    def _println(self, s: str = '') -> None:
        self._ui.write(s)
        self._ui.write('\n')

    def _read_yn(self, prompt: str, *, default: bool | None = None) -> bool:
        ret = self._ui.read_yn(prompt, default=default)
        self._ui.write('\n')
        return ret

    def _read_line(self,
                   prompt: str,
                   *,
                   check: _InputChecker = _check_any) -> str:
        ret = self._ui.read_line(prompt, check=check)
        self._ui.write('\n')
        return ret

    def _read_enter(self) -> None:
        self._ui.read_enter()
        self._ui.write('\n')

    def _is_windows(self) -> bool:
        return os.name == 'nt'

    @staticmethod
    def _gitcookies() -> str:
        """Path to user's gitcookies.

        Can be mocked for testing.
        """
        return os.path.expanduser('~/.gitcookies')


class _CookiefileInfo(NamedTuple):
    """Result for _parse_cookiefile."""
    contains_gerrit: bool
    contains_nongerrit: bool


def _parse_cookiefile(f: TextIO) -> _CookiefileInfo:
    """Checks cookie file contents.

    Used to guide auth configuration.
    """
    contains_gerrit = False
    contains_nongerrit = False
    for line in f:
        if line.lstrip().startswith('#'):
            continue
        if not line.strip():
            continue
        if '.googlesource.com' in line:
            contains_gerrit = True
        else:
            contains_nongerrit = True
    return _CookiefileInfo(
        contains_gerrit=contains_gerrit,
        contains_nongerrit=contains_nongerrit,
    )


def _is_gerrit_url(url: str) -> bool:
    """Checks if URL is for a Gerrit host."""
    if not url:
        return False
    parts = urllib.parse.urlsplit(url)
    if parts.netloc.endswith('.googlesource.com') or parts.netloc.endswith(
            '.git.corp.google.com'):
        return True
    return False


def _url_gerrit_sso_url(parts: urllib.parse.SplitResult) -> str:
    """Return the base SSO URL for a Gerrit host URL."""
    return f'sso://{_url_shortname(parts)}/'


def _url_git_root_url(parts: urllib.parse.SplitResult) -> str:
    """Format URL as Gerrit host URL with root path.

    Example: https://chromium.googlesource.com/
    """
    return parts._replace(netloc=_url_git_host(parts),
                          path='/',
                          query='',
                          fragment='').geturl()


def _url_review_root_url(parts: urllib.parse.SplitResult) -> str:
    """Format URL as Gerrit review host URL with root path.

    Example: https://chromium-review.googlesource.com/
    """
    return parts._replace(netloc=_url_review_host(parts),
                          path='/',
                          query='',
                          fragment='').geturl()


def _url_host_url(parts: urllib.parse.SplitResult) -> str:
    """Format URL with host only (no path).

    Example: https://chromium.googlesource.com
    Example: https://chromium-review.googlesource.com
    """
    return parts._replace(path='', query='', fragment='').geturl()


def _url_git_host(parts: urllib.parse.SplitResult) -> str:
    """Format URL as Gerrit host.

    Example: chromium.googlesource.com
    """
    return f'{_url_shortname(parts)}.googlesource.com'


def _url_review_host(parts: urllib.parse.SplitResult) -> str:
    """Format URL as Gerrit review host.

    Example: chromium-review.googlesource.com
    """
    return f'{_url_shortname(parts)}-review.googlesource.com'


def _url_shortname(parts: urllib.parse.SplitResult) -> str:
    """Format URL as Gerrit host shortname.

    Example: chromium
    """
    name: str = parts.netloc.split('.')[0]
    if name.endswith('-review'):
        name = name[:-len('-review')]
    return name

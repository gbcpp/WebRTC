# Copyright 2025 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from recipe_engine import post_process, recipe_api, turboci

from PB.turboci.graph.orchestrator.v1.check_kind import CheckKind
from PB.turboci.graph.orchestrator.v1.check_state import CheckState
from PB.turboci.graph.orchestrator.v1.workplan import WorkPlan
from PB.turboci.data.gerrit.v1.gerrit_change_info import GerritChangeInfo
from PB.turboci.data.chrome.depot_tools.v1.bot_update_results import (
    BotUpdateResults)
from PB.turboci.data.gerrit.v1.gob_source_check_options import (
    GobSourceCheckOptions)
from PB.turboci.data.gerrit.v1.gob_source_check_results import (
    GobSourceCheckResults)

DEPS = [
    'bot_update',
    'gclient',
    'recipe_engine/assertions',
    'recipe_engine/buildbucket',
    'recipe_engine/path',
    'recipe_engine/properties',
]

PROPERTIES = {
    'turboci_check_id': recipe_api.Property(),
    'bar_revision': recipe_api.Property(default='refs/heads/bar'),
}

_FOO_REPO_URL = 'https://fake-host.googlesource.com/foo'
_BAR_REPO_URL = 'https://fake-host.googlesource.com/bar'


def RunSteps(api, turboci_check_id: str | None, bar_revision: str):
  gclient_config = api.gclient.make_config()

  s = gclient_config.solutions.add()
  s.url = _FOO_REPO_URL
  s.name = 'foo'

  s = gclient_config.solutions.add()
  s.url = _BAR_REPO_URL
  s.name = 'bar'
  s.revision = bar_revision

  api.bot_update.ensure_checkout(gclient_config,
                                 turboci_check_id=turboci_check_id)


def GenTests(api):
  yield api.test(
      'no-check-ci',
      api.properties(turboci_check_id=None),
      api.buildbucket.ci_build(git_repo=_FOO_REPO_URL),
      api.bot_update.repo_urls({
          'foo': f'{_FOO_REPO_URL}.git',
          'bar': f'{_BAR_REPO_URL}.git',
      }),
      api.post_process(post_process.DropExpectation),
      api.assert_workplan(
          lambda assert_, workplan: assert_(not workplan.checks)),
  )

  yield api.test(
      'no-check-try',
      api.properties(turboci_check_id=None),
      api.buildbucket.try_build(git_repo=_FOO_REPO_URL),
      api.bot_update.repo_urls({
          'foo': f'{_FOO_REPO_URL}.git',
          'bar': f'{_BAR_REPO_URL}.git',
      }),
      api.post_process(post_process.DropExpectation),
      api.assert_workplan(
          lambda assert_, workplan: assert_(not workplan.checks)),
  )

  def check_ci_workplan_assert(assert_, workplan: WorkPlan):
    check_id = 'fake-check-id'
    check = turboci.get_check_by_short_id(workplan, check_id)

    assert_(check.kind == CheckKind.CHECK_KIND_SOURCE)
    assert_(check.state == CheckState.CHECK_STATE_FINAL)

    gob_source_check_options = turboci.get_option(GobSourceCheckOptions,
                                                  check)
    expected_gob_source_check_options = GobSourceCheckOptions(
        base_pinned_repos=GobSourceCheckOptions.PinnedRepoMounts(
            mount_overrides=[
                GobSourceCheckOptions.PinnedRepoMounts.MountOverride(
                    mount='bar',
                    override=GobSourceCheckOptions.PinnedRepoMounts.GitCommit(
                        ref='refs/heads/good-bar',
                        id='b' * 40,
                    ),
                ),
                GobSourceCheckOptions.PinnedRepoMounts.MountOverride(
                    mount='foo',
                    override=GobSourceCheckOptions.PinnedRepoMounts.GitCommit(
                        ref='refs/heads/foo',
                        id='a' * 40,
                    ),
                ),
            ]))
    assert_(gob_source_check_options == expected_gob_source_check_options)

    gob_source_check_results = turboci.get_results(GobSourceCheckResults,
                                                   check)
    expected_gob_source_check_results = [
        GobSourceCheckResults(),
    ]
    assert_(gob_source_check_results == expected_gob_source_check_results)

    bot_update_check_results = turboci.get_results(BotUpdateResults, check)
    expected_bot_update_check_results = [
        BotUpdateResults(
            manifest={
                'bar':
                BotUpdateResults.GitCommit(
                    host='fake-host',
                    project='bar',
                    id='b' * 40,
                ),
                'foo':
                BotUpdateResults.GitCommit(
                    host='fake-host',
                    project='foo',
                    id='a' * 40,
                ),
            }),
    ]
    assert_(bot_update_check_results == expected_bot_update_check_results)


  yield api.test(
      'check-ci',
      api.properties(
          turboci_check_id='fake-check-id',
          bar_revision='refs/heads/good-bar:' + 'b' * 40,
      ),
      api.buildbucket.ci_build(
          git_repo=_FOO_REPO_URL,
          git_ref='refs/heads/foo',
          revision='a' * 40,
      ),
      api.bot_update.repo_urls({
          'foo': f'{_FOO_REPO_URL}.git',
          'bar': f'{_BAR_REPO_URL}.git',
      }),
      api.assert_workplan(check_ci_workplan_assert),
      api.post_process(post_process.DropExpectation),
  )

  def check_ci_revision_only_workplan_assert(assert_, workplan: WorkPlan):
    check_id = 'fake-check-id'
    check = turboci.get_check_by_short_id(workplan, check_id)

    assert_(check.kind == CheckKind.CHECK_KIND_SOURCE)
    assert_(check.state == CheckState.CHECK_STATE_FINAL)

    gob_source_check_options = turboci.get_option(GobSourceCheckOptions,
                                                  check)
    expected_gob_source_check_options = GobSourceCheckOptions(
        base_pinned_repos=GobSourceCheckOptions.PinnedRepoMounts(
            mount_overrides=[
                GobSourceCheckOptions.PinnedRepoMounts.MountOverride(
                    mount='bar',
                    override=GobSourceCheckOptions.PinnedRepoMounts.GitCommit(
                        ref='refs/heads/good-bar'),
                ),
                GobSourceCheckOptions.PinnedRepoMounts.MountOverride(
                    mount='foo',
                    override=GobSourceCheckOptions.PinnedRepoMounts.GitCommit(
                        id='a' * 40),
                ),
            ]))
    assert_(gob_source_check_options == expected_gob_source_check_options)

    gob_source_check_results = turboci.get_results(GobSourceCheckResults,
                                                   check)
    expected_gob_source_check_results = [
        GobSourceCheckResults(),
    ]
    assert_(gob_source_check_results == expected_gob_source_check_results)

    bot_update_check_results = turboci.get_results(BotUpdateResults, check)
    expected_bot_update_check_results = [
        BotUpdateResults(
            manifest={
                'bar':
                BotUpdateResults.GitCommit(
                    host='fake-host',
                    project='bar',
                    id='b' * 40,
                ),
                'foo':
                BotUpdateResults.GitCommit(
                    host='fake-host',
                    project='foo',
                    id='a' * 40,
                ),
            }),
    ]
    assert_(bot_update_check_results == expected_bot_update_check_results)

  yield api.test(
      'check-ci-revision-only',
      api.properties(
          turboci_check_id='fake-check-id',
          bar_revision='refs/heads/good-bar',
      ),
      api.buildbucket.ci_build(
          git_repo=_FOO_REPO_URL,
          git_ref=None,
          revision='a' * 40,
      ),
      api.bot_update.revisions({'bar': 'b' * 40}),
      api.bot_update.repo_urls({
          'foo': f'{_FOO_REPO_URL}.git',
          'bar': f'{_BAR_REPO_URL}.git',
      }),
      api.assert_workplan(check_ci_revision_only_workplan_assert),
      api.post_process(post_process.DropExpectation),
  )

  def check_try_workplan_assert(assert_, workplan: WorkPlan):
    check_id = 'fake-check-id'
    check = turboci.get_check_by_short_id(workplan, check_id)

    assert_(check.kind == CheckKind.CHECK_KIND_SOURCE)
    assert_(check.state == CheckState.CHECK_STATE_FINAL)

    gob_source_check_options = turboci.get_option(GobSourceCheckOptions,
                                                  check)
    expected_gob_source_check_options = GobSourceCheckOptions(
        gerrit_changes=[
            GobSourceCheckOptions.GerritChange(
                hostname='fake-host',
                change_number=123456,
                patchset=7,
                mounts_to_apply=['foo'],
            ),
        ],
        base_pinned_repos=GobSourceCheckOptions.PinnedRepoMounts(
            mount_overrides=[
                GobSourceCheckOptions.PinnedRepoMounts.MountOverride(
                    mount='bar',
                    override=GobSourceCheckOptions.PinnedRepoMounts.GitCommit(
                        ref='refs/heads/good-bar'),
                ),
                GobSourceCheckOptions.PinnedRepoMounts.MountOverride(
                    mount='foo',
                    override=GobSourceCheckOptions.PinnedRepoMounts.GitCommit(
                        ref='refs/heads/main'),
                ),
            ]),
    )
    assert_(gob_source_check_options == expected_gob_source_check_options)

    gob_source_check_results = turboci.get_results(GobSourceCheckResults,
                                                   check)
    expected_gob_source_check_results = [
        GobSourceCheckResults(changes=[
            GerritChangeInfo(
                host='fake-host',
                project='foo',
                branch='main',
                full_branch='refs/heads/main',
                change_number=123456,
                patchset=7,
            ),
        ]),
    ]
    assert_(gob_source_check_results == expected_gob_source_check_results)

    bot_update_check_results = turboci.get_results(BotUpdateResults, check)
    expected_bot_update_check_results = [
        BotUpdateResults(
            manifest={
                'bar':
                BotUpdateResults.GitCommit(
                    host='fake-host',
                    project='bar',
                    id='b' * 40,
                ),
                'foo':
                BotUpdateResults.GitCommit(
                    host='fake-host',
                    project='foo',
                    id='a' * 40,
                ),
            }),
    ]
    assert_(bot_update_check_results == expected_bot_update_check_results)

  yield api.test(
      'check-try',
      api.properties(
          turboci_check_id='fake-check-id',
          bar_revision='refs/heads/good-bar',
      ),
      api.buildbucket.try_build(
          git_repo=_FOO_REPO_URL,
          change_number=123456,
          patch_set=7,
      ),
      api.bot_update.revisions({
          'foo': 'a' * 40,
          'bar': 'b' * 40,
      }),
      api.bot_update.repo_urls({
          'foo': f'{_FOO_REPO_URL}.git',
          'bar': f'{_BAR_REPO_URL}.git',
      }),
      api.assert_workplan(check_try_workplan_assert),
      api.post_process(post_process.DropExpectation),
  )

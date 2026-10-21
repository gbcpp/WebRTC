# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Recipe module to ensure a checkout is consistent on a bot."""

import abc
import collections.abc
import dataclasses
import typing

from recipe_engine import recipe_api, turboci
from recipe_engine.config_types import Path

from PB.go.chromium.org.luci.buildbucket.proto import common as common_pb2
from PB.turboci.data.chrome.depot_tools.v1.bot_update_results import (
    BotUpdateResults)
from PB.turboci.data.gerrit.v1.gob_source_check_options import (
    GobSourceCheckOptions)
from PB.turboci.data.gerrit.v1.gob_source_check_results import (
    GobSourceCheckResults)

@dataclasses.dataclass(kw_only=True, frozen=True)
class RelativeRoot:
  """A root that is relative to the checkout root.

  Attributes:
    name: The name of the root/the path to the root relative to the checkout
      directory.
    path: The absolute path to the root.
  """
  name: str
  path: Path

  @classmethod
  def create(cls, checkout_dir: Path, name: str) -> typing.Self:
    return cls(name=name, path=checkout_dir / name)


class ManifestRepo(typing.TypedDict):
  repository: str
  revision: str


@dataclasses.dataclass(kw_only=True, frozen=True)
class Result:
  """The noteworthy paths for a source checkout.

  Attributes:
    checkout_dir: The directory where the checkout was performed.
    source_root: The root for the repo identified by the first gclient solution.
    patch_root: The root for the repo that was patched, if a patch was applied.
      Otherwise, None.
    properties: The properties set by the bot_update execution.
    manifest: The manifest mapping the checkout_dir-relative path to the
      repository and revision that was checked out.
    fixed_revisions: The explicitly requested revisions; a mapping from the
      checkout_dir-relative path to the requested revision.
    out_commit: Gitiles output commit derived from got_revision.
  """
  # Directories relevant to the checkout
  checkout_dir: Path
  source_root: RelativeRoot
  patch_root: RelativeRoot | None = None

  # Details about the revisions that were checked out
  properties: dict[str, str]
  manifest: dict[str, ManifestRepo]
  fixed_revisions: dict[str, str]

  out_commit: common_pb2.GitilesCommit | None


class _TurboCICheckHandler(abc.ABC):
  """Handler for creating and updating a TurboCI source check.

  Getting a handler should be done by calling
  _TurboCICheckHandler.create with the ID to use for the check. An empty
  check ID will result in a no-op handler.

  Before performing the checkout, set_revisions should be called to
  provide information about the known revisions being checked out and if
  a patch is being applied, set_gerrit_change should be called to
  provide information about the change. After those calls are made,
  create_check should be called to create the check in TurboCI.

  After performing the checkout, set_result should be called to write
  results into the check and finalize it.
  """

  @staticmethod
  def create(api, check_id: str):
    """Create a _TurboCiCheckHandler.

    Args:
      check_id: The ID of the TurboCI check that the handler should
        create. If empty, a no-op handler will be returned.
    """
    if not check_id:
      return _DisabledTurboCICheckHandler()

    return _EnabledTurboCiCheckHandler(api, check_id)

  @abc.abstractmethod
  def set_gerrit_change(self, gerrit_change: common_pb2.GerritChange,
                        patch_root: str) -> None:
    """Sets the gerrit change that is being checked out.

    Information about the change will be added to the check that is
    created.

    Args:
      gerrit_change: The gerrit change that is being checked out.
      patch_root: The path to the repository that is being patched,
        relative to the directory where the checkout is performed.
    """
    raise NotImplementedError()  # pragma: no cover

  @abc.abstractmethod
  def set_revisions(
      self,
      revisions: collections.abc.Mapping[str, str],
      refs: collections.abc.Mapping[str, str],
  ) -> None:
    """Set the revisions to be checked out.

    Information about the revisions will be added to the check that is
    created.

    Args:
      revisions: Mapping from the solution name/checkout-relative path
        of a repo to the revision that the repo will be checked out
        from.
      refs: Mapping from the solution name/checkout-relative path of a
        repo to the ref that the repo will be checked out from.
    """
    raise NotImplementedError()  # pragma: no cover

  @abc.abstractmethod
  def create_check(self) -> None:
    """Create the TurboCI check.

    A check will be created with kind SOURCE and state PLANNED. The
    check will contain a GobSourceCheckOptions option that contains the
    revision information specified by set_revisions and the change
    information specified by set_gerrit_change.
    """
    raise NotImplementedError()  # pragma: no cover

  @abc.abstractmethod
  def set_result(self, result: Result) -> None:
    """Set the results on the TurboCI check.

    The check will have a GobSourceCheckResults result added that
    contains details about the change that was applied (if any) and be
    moved to the FINAL state.
    """
    raise NotImplementedError()  # pragma: no cover


class _DisabledTurboCICheckHandler(_TurboCICheckHandler):
  """A no-op implementation of _TurboCICheckHandler."""

  def set_gerrit_change(self, gerrit_change: common_pb2.GerritChange,
                        patch_root: str) -> None:
    pass

  def set_revisions(
      self,
      revisions: collections.abc.Mapping[str, str],
      refs: collections.abc.Mapping[str, str],
  ) -> None:
    pass

  def create_check(self):
    pass

  def set_result(self, result: Result) -> None:
    pass


class _EnabledTurboCiCheckHandler(_TurboCICheckHandler):
  """_TurboCICheckHandler that actually creates a check in TurboCI."""

  def __init__(self, api, check_id: str):
    self._api = api
    self._check_id = check_id
    self._gerrit_change: common_pb2.GerritChange | None = None
    self._source_check_options = GobSourceCheckOptions()

  def set_gerrit_change(self, gerrit_change: common_pb2.GerritChange,
                        patch_root: str) -> None:
    self._gerrit_change = gerrit_change
    self._source_check_options.gerrit_changes.add(
        # TurboCI uses the HOST name
        # https://source.chromium.org/chromium/infra/infra_superproject/+/main:recipes-py/recipe_proto/turboci/data/gerrit/v1/gob_source_check_options.proto;l=22-25;drc=d0c1eac8c3953c26af1b01aa9ab8fe988cb92bc3
        hostname=gerrit_change.host.removesuffix('-review.googlesource.com'),
        change_number=gerrit_change.change,
        patchset=gerrit_change.patchset,
        mounts_to_apply=[patch_root],
    )

  def set_revisions(
      self,
      revisions: collections.abc.Mapping[str, str],
      refs: collections.abc.Mapping[str, str],
  ) -> None:
    pinned_repo_mounts = self._source_check_options.base_pinned_repos
    for name, revision in sorted(revisions.items()):
      # Handle the "ref:revision" syntax, e.g. refs/branch-heads/4.2:deadbeef
      if ':' in revision:
        ref, commit_id = revision.split(':', 1)
      elif revision.startswith('refs'):
        ref = revision
        commit_id = None
      else:
        commit_id = revision
        ref = refs.get(name)
      pinned_repo_mounts.mount_overrides.add(
          mount=name,
          override=GobSourceCheckOptions.PinnedRepoMounts.GitCommit(
              # TODO: crbug.com/443496677 - set host and project
              id=commit_id,
              ref=ref,
          ),
      )

  def create_check(self) -> None:
    turboci.write_nodes(
        # TODO: crbug.com/443496677 - Add some structured data to the reason
        turboci.reason('executing bot_update'),
        turboci.check(
            self._check_id,
            kind='CHECK_KIND_SOURCE',
            options=[self._source_check_options],
            state='CHECK_STATE_PLANNED',
        ),
    )

  def set_result(self, result: Result) -> None:
    gob_source_check_results = GobSourceCheckResults()
    if self._gerrit_change:
      gob_source_check_results.changes.add(
          # TurboCI uses the HOST name
          # https://source.chromium.org/chromium/infra/infra_superproject/+/main:recipes-py/recipe_proto/turboci/data/gerrit/v1/gerrit_change_info.proto;l=26-32;drc=48b620356e842ea19ec908f3cb18b1a0cb555d26
          host=self._gerrit_change.host.removesuffix(
              '-review.googlesource.com'),
          project=self._gerrit_change.project,
          branch=self._api.m.tryserver.gerrit_change_target_ref.removeprefix(
              'refs/heads/'),
          full_branch=self._api.m.tryserver.gerrit_change_target_ref,
          change_number=self._gerrit_change.change,
          patchset=self._gerrit_change.patchset,
          # TODO: crbug.com/443496677 - Fill in status, creation_time,
          # last_modification_time, submitted_time, current_revision, revisions,
          # owner, reviewers, labels, messages, change_id, topic, is_owner_bot?
      )
    bot_update_check_results = BotUpdateResults()
    for path, manifest_commit in result.manifest.items():
      host, project = self._api.m.gitiles.parse_repo_url(
          manifest_commit['repository'])
      commit = bot_update_check_results.manifest[path]
      commit.host = host.removesuffix('.googlesource.com')
      commit.project = project
      commit.id = manifest_commit['revision']

    # TODO: crbug.com/443496677 - Add a result type to expose the bot_update
    # manifest
    turboci.write_nodes(
        turboci.reason('bot_update completed'),
        turboci.check(
            self._check_id,
            results=[gob_source_check_results, bot_update_check_results],
            state='CHECK_STATE_FINAL',
        ))

class BotUpdateApi(recipe_api.RecipeApi):

  def __init__(self, properties, deps_revision_overrides, *args, **kwargs):
    self._deps_revision_overrides = deps_revision_overrides

    self._last_returned_properties = {}
    super(BotUpdateApi, self).__init__(*args, **kwargs)
    self._bot_update_properties = properties

  def __call__(self, name, cmd, **kwargs):
    """Wrapper for easy calling of bot_update."""
    assert isinstance(cmd, (list, tuple))
    bot_update_path = self.resource('bot_update.py')
    kwargs.setdefault('infra_step', True)

    # Reserve 1 minute to upload traces.
    # TODO(gavinmak): Reserve from grace_period once https://crbug.com/1305422
    # is fixed.
    deadline = self.m.context.deadline
    if deadline.soft_deadline:  # pragma: no cover
      deadline.soft_deadline -= 60

    with self.m.context(env=self._get_bot_update_env(), deadline=deadline):
      with self.m.depot_tools.on_path():
        return self.m.step(name,
                           ['vpython3', '-u', bot_update_path] + cmd,
                           **kwargs)

  @property
  def last_returned_properties(self):
    return self._last_returned_properties

  def _get_commit_repo_path(self, commit, gclient_config):
    """Returns local path to the repo that the commit is associated with.

    The commit must be a self.m.buildbucket.common_pb2.GitilesCommit.
    If commit does not specify any repo, returns name of the first solution.

    Raises an InfraFailure if the commit specifies a repo unexpected by gclient.
    """
    assert gclient_config.solutions, 'gclient_config.solutions is empty'

    # if repo is not specified, choose the first solution.
    if not (commit.host and commit.project):
      return gclient_config.solutions[0].name
    assert commit.host and commit.project

    repo_url = self.m.gitiles.unparse_repo_url(commit.host, commit.project)
    repo_path = self.m.gclient.get_repo_path(
        repo_url, gclient_config=gclient_config)
    if not repo_path:
      raise self.m.step.InfraFailure(
          'invalid (host, project) pair in '
          'buildbucket.build.input.gitiles_commit: '
          '(%s, %s) does not match any of configured gclient solutions '
          'and not present in gclient_config.repo_path_map' % (
              commit.host, commit.project))

    return repo_path

  def _get_bot_update_env(self):
    # TODO(gavinmak): Use mkdtemp when crbug.com/1457059 is fixed.
    self._trace_dir = self.m.path.cleanup_dir

    # If a Git HTTP request is constantly below GIT_HTTP_LOW_SPEED_LIMIT
    # bytes/second for GIT_HTTP_LOW_SPEED_TIME seconds then such request will be
    # aborted. Otherwise, it would wait for global timeout to be reached.
    env = {
        # CHROME_HEADLESS makes it so we don't create gclient's _bad_scm dir
        # and instead just remove/restart checkout from scratch.
        'CHROME_HEADLESS':
        '1',
        'GIT_HTTP_LOW_SPEED_LIMIT':
        '102400',  # in bytes
        'GIT_HTTP_LOW_SPEED_TIME':
        1800,  # in seconds
        'GIT_TRACE2_EVENT':
        self.m.path.join(self._trace_dir, 'trace2-event'),
        'GIT_TRACE_CURL':
        self.m.path.join(self._trace_dir, 'trace-curl'),
        'GIT_TRACE_CURL_NO_DATA':
        1,
        'GIT_TRACE_PACKET':
        self.m.path.join(self._trace_dir, 'trace-packet'),
        'GIT_BACKENDINFO':
        1,
        'GIT_DAPPER_TRACE':
        1,
        'GIT_SSH_COMMAND':
        'ssh -o SendEnv=GIT_DAPPER_TRACE -o SendEnv=GIT_BACKENDINFO'
    }

    if self.m.buildbucket.build.id == 0:
      env['DEPOT_TOOLS_COLLECT_METRICS'] = '0'
    else:
      env['DEPOT_TOOLS_REPORT_BUILD'] = '%s/%s/%s/%s' % (
          self.m.buildbucket.build.builder.project,
          self.m.buildbucket.build.builder.bucket,
          self.m.buildbucket.build.builder.builder, self.m.buildbucket.build.id)

    if 'stale_process_duration_override' in self._bot_update_properties:
      env['STALE_PROCESS_DURATION'] = self._bot_update_properties[
          'stale_process_duration_override']
    return env

  def _upload_traces(self):
    with self.m.step.nest('upload git traces') as presentation:
      id = str(self.m.buildbucket.build.id
               or self.m.led.run_id.replace('/', '_'))
      dest = self.m.path.join(self._trace_dir, '%s.zip' % id)
      zip_path = self.m.archive.package(self._trace_dir) \
                  .with_file(self._trace_dir / 'trace2-event') \
                  .with_file(self._trace_dir / 'trace-curl') \
                  .with_file(self._trace_dir / 'trace-packet') \
                  .archive('compress traces', dest, 'zip')
      try:
        # Don't upload with a destination path, otherwise we have to grant bots
        # storage.objects.list permisson on this bucket.
        self.m.gsutil(['cp', zip_path, 'gs://chrome-bot-traces'], name='upload')
      except self.m.step.StepFailure:
        presentation.status = self.m.step.INFRA_FAILURE
        presentation.step_text = ('Failed to upload traces. '
                                  'File a bug under Infra>SDK to adjust ACLs.')

  def ensure_checkout(self,
                      gclient_config=None,
                      *,
                      suffix=None,
                      patch=True,
                      update_presentation=True,
                      patch_root=None,
                      with_branch_heads=False,
                      with_tags=False,
                      no_fetch_tags=False,
                      refs=None,
                      clobber=False,
                      root_solution_revision=None,
                      gerrit_no_reset=False,
                      gerrit_no_rebase_patch_ref=False,
                      assert_one_gerrit_change=True,
                      patch_refs=None,
                      ignore_input_commit=False,
                      add_blamelists=False,
                      set_output_commit=False,
                      step_test_data=None,
                      enforce_fetch=False,
                      download_topics=False,
                      recipe_revision_overrides=None,
                      step_tags=None,
                      clean_ignored=False,
                      turboci_check_id: str = '',
                      **kwargs):
    """
    Args:
      * gclient_config: The gclient configuration to use when running bot_update.
        If omitted, the current gclient configuration is used.
      * no_fetch_tags: When true, the root git repo being checked out will not
        fetch any tags referenced from the references being fetched. When a repo
        has many references, it can become a performance bottleneck, so avoid
        tags if the checkout will not need them present.
      * ignore_input_commit: if True, ignore api.buildbucket.gitiles_commit.
        Exists for historical reasons. Please do not use.
      * add_blamelists: if True, add blamelist pins for all of the repos that had
        revisions specified in the gclient config.
      * set_output_commit: if True, mark the checked out commit as the
        primary output commit of this build, i.e. call
        api.buildbucket.set_output_gitiles_commit.
        In case of multiple repos, the repo is the one specified in
        api.buildbucket.gitiles_commit or the first configured solution.
        When sorting builds by commit position, this commit will be used.
        Requires falsy ignore_input_commit.
      * step_test_data: a null function that returns test bot_update.py output.
        Use test_api.output_json to generate test data.
      * enforce_fetch: Enforce a new fetch to refresh the git cache, even if the
        solution revision passed in already exists in the current git cache.
      * assert_one_gerrit_change: if True, assert that there is at most one
        change in self.m.buildbucket.build.input.gerrit_changes, because
        bot_update module ONLY supports one change. Users may specify a change
        via tryserver.set_change() and explicitly set this flag False.
      * download_topics: If True, gclient downloads and patches locally from all
        open Gerrit CLs that have the same topic as the tested patch ref.
      * recipe_revision_overrides: a dict {deps_name: revision} of revision
        overrides passed in from the recipe. These should be revisions unique
        to each particular build/recipe run. e.g. the recipe might parse a gerrit
        change's commit message to get this revision override requested by the
        author.
      * step_tags: a dict {tag name: tag value} of tags to add to the step
      * clean_ignored: If True, also clean ignored files from the checkout.
      * turboci_check_id: If non-empty, a turboci source check will be created
        representing the checkout that will be performed with results set to
        indicate the code that was checked out. An InfraFailure will be raised
        if a non-empty value is provided and the gclient config doesn't have
        exactly 1 solution.
    """
    assert not (ignore_input_commit and set_output_commit)
    if assert_one_gerrit_change:
      assert len(self.m.buildbucket.build.input.gerrit_changes) <= 1, (
          'bot_update does not support more than one '
          'buildbucket.build.input.gerrit_changes')

    refs = refs or []
    # We can re-use the gclient spec from the gclient module, since all the
    # data bot_update needs is already configured into the gclient spec.
    cfg = gclient_config or self.m.gclient.c
    assert cfg is not None, (
        'missing gclient_config or forgot api.gclient.set_config(...) before?')

    check_handler = _TurboCICheckHandler.create(self, turboci_check_id)

    # Construct our bot_update command.  This basically be inclusive of
    # everything required for bot_update to know:
    patch_root = patch_root or self.m.gclient.get_gerrit_patch_root(
        gclient_config=cfg)

    # Allow patched project's revision if necessary.
    # This is important for projects which are checked out as DEPS of the
    # gclient solution.
    self.m.gclient.set_patch_repo_revision(cfg)

    reverse_rev_map = self.m.gclient.got_revision_reverse_mapping(cfg)

    flags = [
        # What do we want to check out (spec/root/rev/reverse_rev_map).
        ['--spec-path', self.m.raw_io.input(
            self.m.gclient.config_to_pythonish(cfg))],
        ['--patch_root', patch_root],
        ['--revision_mapping_file', self.m.json.input(reverse_rev_map)],
        ['--git-cache-dir', cfg.cache_dir],
        ['--cleanup-dir', self.m.path.cleanup_dir / 'bot_update'],

        # Hookups to JSON output back into recipes.
        ['--output_json', self.m.json.output()],
    ]

    # How to find the patch, if any
    if patch:
      if self.m.tryserver.gerrit_change:
        check_handler.set_gerrit_change(self.m.tryserver.gerrit_change,
                                        patch_root)

      repo_url = self.m.tryserver.gerrit_change_repo_url
      fetch_ref = self.m.tryserver.gerrit_change_fetch_ref
      target_ref = self.m.tryserver.gerrit_change_target_ref
      if repo_url and fetch_ref:
        flags.append([
            '--patch_ref',
            '%s@%s:%s' % (repo_url, target_ref, fetch_ref),
        ])
      if patch_refs:
        flags.extend(
            ['--patch_ref', patch_ref]
            for patch_ref in patch_refs)

    # Compute requested revisions.
    revisions = {}
    for solution in cfg.solutions:
      if solution.revision:
        revisions[solution.name] = solution.revision

    # HACK: ensure_checkout API must be redesigned so that we don't pass such
    # parameters. Existing semantics is too opiniated.
    in_commit = self.m.buildbucket.gitiles_commit
    in_commit_rev = in_commit.id or in_commit.ref
    in_commit_repo_path = None
    if not ignore_input_commit and in_commit_rev:
      # Note: this is not entirely correct. build.input.gitiles_commit
      # definition says "The Gitiles commit to run against.".
      # However, here we ignore it if the config specified a revision.
      # This is necessary because existing builders rely on this behavior,
      # e.g. they want to force refs/heads/main at the config level.
      in_commit_repo_path = self._get_commit_repo_path(in_commit, cfg)
      # The repo_path that comes back on Windows will have backslashes, which
      # won't match the paths that the gclient configs and bot_update script use
      in_commit_repo_path = in_commit_repo_path.replace(self.m.path.sep, '/')
      revisions[in_commit_repo_path] = (
          revisions.get(in_commit_repo_path) or in_commit_rev)
      parsed_solution_urls = set(
          self.m.gitiles.parse_repo_url(s.url) for s in cfg.solutions)
      if (in_commit.id and in_commit.ref
          and (in_commit.host, in_commit.project) in parsed_solution_urls):
        refs = [in_commit.ref] + refs

    # Guarantee that first solution has a revision.
    # TODO(machenbach): We should explicitly pass HEAD for ALL solutions
    # that don't specify anything else.
    first_sln = cfg.solutions[0].name
    revisions[first_sln] = revisions.get(first_sln) or 'HEAD'

    if cfg.revisions:
      # Only update with non-empty values. Some recipe might otherwise
      # overwrite the HEAD default with an empty string.
      revisions.update(
          (k, v) for k, v in cfg.revisions.items() if v)
    if cfg.solutions and root_solution_revision:
      revisions[first_sln] = root_solution_revision
    # Allow for overrides required to bisect into rolls.
    revisions.update(self._deps_revision_overrides)

    # Set revision overrides passed in from the calling recipe
    if recipe_revision_overrides:
      revisions.update(recipe_revision_overrides)

    # Compute command-line parameters for requested revisions.
    # Also collect all fixed revisions to simulate them in the json output.
    # Fixed revision are the explicit input revisions of bot_update.py, i.e.
    # every command line parameter "--revision name@value".
    fixed_revisions = {}
    for name, revision in sorted(revisions.items()):
      fixed_revision = self.m.gclient.resolve_revision(revision)
      if fixed_revision:
        if fixed_revision.upper() == 'HEAD' and patch:
          # Sync to correct destination ref
          fixed_revision = self._destination_ref(cfg, name)
        fixed_revisions[name] = fixed_revision
        # If we're syncing to a ref, we want to make sure it exists before
        # trying to check it out.
        if (fixed_revision.startswith('refs/') and
            # TODO(crbug.com/874501): fetching additional refs is currently
            # only supported for the root solution. We should investigate
            # supporting it for other dependencies.
            cfg.solutions and
            cfg.solutions[0].name == name):
          # Handle the "ref:revision" syntax, e.g.
          # refs/branch-heads/4.2:deadbeef
          refs.append(fixed_revision.split(':')[0])
        flags.append(['--revision', '%s@%s' % (name, fixed_revision)])

    turboci_refs = {}
    if (in_commit_repo_path and in_commit.ref
        and revisions.get(in_commit_repo_path) == in_commit.id):
      turboci_refs[in_commit_repo_path] = in_commit.ref
    check_handler.set_revisions(fixed_revisions, turboci_refs)

    for ref in refs:
      assert not ref.startswith('refs/remotes/'), (
          'The "refs/remotes/*" syntax is not supported.\n'
          'The "remotes" syntax is dependent on the way the local repo is '
          'configured, and while there are defaults that can often be '
          'assumed, there is no guarantee the mapping will always be done in '
          'a particular way.')

    # Add extra fetch refspecs.
    for ref in refs:
      flags.append(['--refs', ref])

    # Filter out flags that are None.
    cmd = [item for flag_set in flags
           for item in flag_set if flag_set[1] is not None]

    if clobber:
      cmd.append('--clobber')
    if with_branch_heads or cfg.with_branch_heads:
      cmd.append('--with_branch_heads')
    if with_tags or cfg.with_tags:
      cmd.append('--with_tags')
    if gerrit_no_reset:
      cmd.append('--gerrit_no_reset')
    if download_topics:
      cmd.append('--download_topics')
    if enforce_fetch:
      cmd.append('--enforce_fetch')
    if no_fetch_tags:
      cmd.append('--no_fetch_tags')
    if gerrit_no_rebase_patch_ref:
      cmd.append('--gerrit_no_rebase_patch_ref')
    if self.m.properties.get('bot_update_experiments'):
      cmd.append('--experiments=%s' %
          ','.join(self.m.properties['bot_update_experiments']))
    if clean_ignored:
      cmd.append('--clean-ignored')

    # Inject Json output for testing.
    step_test_data = step_test_data or (lambda: self.test_api.output_json(
        first_sln=first_sln,
        revisions=self._test_data.get('revisions', {}),
        fixed_revisions=fixed_revisions,
        got_revision_mapping=reverse_rev_map,
        patch_root=patch_root,
        repo_urls=self._test_data.get('repo_urls', None),
        fail_checkout=self._test_data.get('fail_checkout', False),
        fail_patch=self._test_data.get('fail_patch', False),
        commit_positions=self._test_data.get('commit_positions', True),
    ))

    check_handler.create_check()

    name = self.step_name(patch, suffix)

    # Ah hah! Now that everything is in place, lets run bot_update!
    step_result = None
    ok_ret = (0, 88)
    try:
      # Error code 88 is the 'patch failure' code for patch apply failure.
      step_result = self(name,
                         cmd,
                         step_test_data=step_test_data,
                         ok_ret=ok_ret,
                         **kwargs)
    finally:
      step_result = self.m.step.active_result

      if step_tags:
        for tag, value in step_tags.items():
          step_result.presentation.tags[tag] = value

      # The step_result can be missing the json attribute if the build
      # is shutting down and the bot_update script is not able to finish
      # writing the json output.
      # An AttributeError occuring in this finally block swallows any
      # StepFailure that may bubble up.
      if (step_result and hasattr(step_result, 'json')
          and step_result.json.output):
        result = step_result.json.output
        self._last_returned_properties = result.get('properties', {})

        if update_presentation:
          # Set properties such as got_revision.
          for prop_name, prop_value in (
              self.last_returned_properties.items()):
            step_result.presentation.properties[prop_name] = prop_value

        # Add helpful step description in the step UI.
        if 'step_text' in result:
          step_text = result['step_text']
          step_result.presentation.step_text = step_text

        if result.get('patch_failure'):
          patch_body = result.get('failed_patch_body')
          if patch_body:
            step_result.presentation.logs['patch error'] = (
                patch_body.splitlines())

          if result.get('patch_apply_return_code') == 3:
            # This is download failure, hence an infra failure.
            self._upload_traces()
            raise self.m.step.InfraFailure(
                'Patch failure: Git reported a download failure')
          else:
            # Mark it as failure so we provide useful logs
            # https://crbug.com/1207685
            step_result.presentation.status = 'FAILURE'
            # This is actual patch failure.
            self.m.tryserver.set_patch_failure_tryjob_result()
            self.m.cv.set_do_not_retry_build()
            self._upload_traces()
            raise self.m.step.StepFailure(
                'Patch failure: See patch error log attached to bot_update. '
                'Try rebasing?')

        if (step_result.exc_result.retcode not in ok_ret
            or step_result.exc_result.was_cancelled
            or step_result.exc_result.had_timeout):
          self._upload_traces()

        if add_blamelists and 'manifest' in result:
          blamelist_pins = []
          for name in sorted(revisions):
            m = result['manifest'][name]
            pin = {'id': m['revision']}
            pin['host'], pin['project'] = (
                self.m.gitiles.parse_repo_url(m['repository']))
            blamelist_pins.append(pin)
          self.m.milo.show_blamelist_for(blamelist_pins)

        out_commit = None

        if ('got_revision' in self._last_returned_properties
            and 'got_revision' in reverse_rev_map):
          # As of April 2019, got_revision describes the output commit,
          # the same commit that Build.output.gitiles_commit describes.
          # In particular, users tend to set got_revision to make Milo display
          # it. Derive output commit from got_revision.
          out_commit = common_pb2.GitilesCommit(
              id=self._last_returned_properties['got_revision'],
          )

          out_solution = reverse_rev_map['got_revision']
          out_manifest = result['manifest'][out_solution]
          assert out_manifest['revision'] == out_commit.id, (
              out_manifest, out_commit.id)

          out_commit.host, out_commit.project = (
              self.m.gitiles.parse_repo_url(out_manifest['repository'])
          )

          # Determine the output ref.
          got_revision_cp = self._last_returned_properties.get('got_revision_cp')
          in_rev = self.m.gclient.resolve_revision(revisions.get(out_solution))
          if not in_rev:
            in_rev = 'HEAD'
          if got_revision_cp:
            # If commit position string is available, read the ref from there.
            out_commit.ref, out_commit.position = (
                self.m.commit_position.parse(got_revision_cp))
          elif in_rev.startswith('refs/'):
            # If we were asked to check out a specific ref, use it as output
            # ref.
            out_commit.ref = in_rev
          elif in_rev == 'HEAD':
            # bot_update.py interprets HEAD as refs/heads/main
            out_commit.ref = 'refs/heads/main'
          elif out_commit.id == in_commit.id and in_commit.ref:
            # Derive output ref from the input ref.
            out_commit.ref = in_commit.ref

          if set_output_commit:
            assert out_commit.ref, (
                'Unsupported case. '
                'Call buildbucket.set_output_gitiles_commit directly.')

            self.m.buildbucket.set_output_gitiles_commit(out_commit)

        # Set the "checkout" path for the main solution.
        # This is used by the Chromium module to figure out where to look for
        # the checkout.
        # bot_update actually just sets root to be the folder name of the
        # first solution.
        if (result.get('did_run')
            and 'checkout' not in self.m.path
            and 'root' in result):
          co_root = result['root']
          cwd = self.m.context.cwd or self.m.path.start_dir
          self.m.path.checkout_dir = cwd / co_root

    assert result.get('did_run') and result.get('root')
    checkout_dir = self.m.context.cwd or self.m.path.start_dir
    ret = Result(
        checkout_dir=checkout_dir,
        source_root=RelativeRoot.create(checkout_dir, result['root']),
        patch_root=(RelativeRoot.create(checkout_dir, result['patch_root'])
                    if result['patch_root'] is not None else None),
        properties=result.get('properties', {}),
        manifest=result.get('manifest', {}),
        fixed_revisions=result.get('fixed_revisions', {}),
        out_commit=out_commit,
    )
    check_handler.set_result(ret)
    return ret

  def _destination_ref(self, cfg, path):
    """Returns the ref branch of a CL for the matching project if available or
    HEAD otherwise.

    If there's no Gerrit CL associated with the run, returns 'HEAD'.
    Otherwise this queries Gerrit for the correct destination ref, which
    might differ from refs/heads/main.

    Args:
      * cfg: The used gclient config.
      * path: The DEPS path of the project this prefix is for. E.g. 'src' or
          'src/v8'. The query will only be made for the project that matches
          the CL's project.

    Returns:
        A destination ref as understood by bot_update.py if available
        and if different from refs/heads/main, returns 'HEAD' otherwise.
    """
    # Ignore project paths other than the one belonging to the current CL.
    patch_path = self.m.gclient.get_gerrit_patch_root(gclient_config=cfg)
    if patch_path:
      patch_path = patch_path.replace(self.m.path.sep, '/')
    if not patch_path or path != patch_path:
      return 'HEAD'

    return self.m.tryserver.gerrit_change_target_ref

  def resolve_fixed_revision(self, bot_update_result, name):
    """Sets a fixed revision for a single dependency using project revision
    properties.
    """
    rev_properties = self.get_project_revision_properties(name)
    self.m.gclient.c.revisions = {
        name: bot_update_result.properties[rev_properties[0]]
    }

  def _resolve_fixed_revisions(self, bot_update_result):
    """Sets all fixed revisions from the first sync to their respective
    got_X_revision values.

    If on the first sync, a revision was requested to be HEAD, this avoids
    using HEAD potentially resolving to a different revision on the second
    sync. Instead, we sync explicitly to whatever was checked out the first
    time.

    Example (chromium trybot used with v8 patch):

    First sync was called with
    bot_update.py --revision src@abc --revision src/v8@HEAD
    Fixed revisions are: src, src/v8
    Got_revision_mapping: src->got_revision, src/v8->got_v8_revision
    got_revision = abc, got_v8_revision = deadbeef
    Second sync will be called with
    bot_update.py --revision src@abc --revision src/v8@deadbeef

    Example (chromium trybot used with chromium DEPS change, changing v8 from
    "v8_before" to "v8_after"):

    First sync was called with
    bot_update.py --revision src@abc
    Fixed revisions are: src
    Got_revision_mapping: src->got_revision, src/v8->got_v8_revision
    got_revision = abc, got_v8_revision = v8_after
    Second sync will be called with
    bot_update.py --revision src@abc
    When deapplying the patch, v8 will be synced to v8_before.
    """
    for name in bot_update_result.fixed_revisions:
      rev_properties = self.get_project_revision_properties(name)
      if (rev_properties
          and bot_update_result.properties.get(rev_properties[0])):
        self.m.gclient.c.revisions[name] = str(
            bot_update_result.properties[rev_properties[0]])

  # TODO(machenbach): Replace usages of this method eventually by direct calls
  # to the manifest output.
  def get_project_revision_properties(self, project_name, gclient_config=None):
    """Returns all property names used for storing the checked-out revision of
    a given project.

    Args:
      * project_name (str): The name of a checked-out project as deps path, e.g.
          src or src/v8.
      * gclient_config: The gclient configuration to use. If omitted, the current
          gclient configuration is used.

    Returns (list of str): All properties that'll hold the checked-out revision
        of the given project. An empty list if no such properties exist.
    """
    cfg = gclient_config or self.m.gclient.c
    # Sort for determinism. We might have several properties for the same
    # project, e.g. got_revision and got_webrtc_revision.
    rev_reverse_map = self.m.gclient.got_revision_reverse_mapping(cfg)
    return sorted(
        prop
        for prop, project in rev_reverse_map.items()
        if project == project_name
    )

  def deapply_patch(
      self,
      bot_update_result,
      *,
      turboci_check_id: str = '',
  ):
    """Deapplies a patch, taking care of DEPS and solution revisions properly.

    Args:
      turboci_check_id: The ID of the source check to create for checking out
        the unpatched code. See documentation of the turboci_check_id parameter
        of ensure_checkout for more information.
    """
    # We only override first solution here to make sure that we correctly revert
    # changes to DEPS file, which is particularly important for auto-rolls. It
    # is also imporant that we do not assume that corresponding revision is
    # stored in the 'got_revision' as some gclient configs change the default
    # mapping for their own purposes.
    first_solution_name = self.m.gclient.c.solutions[0].name
    rev_property = self.get_project_revision_properties(first_solution_name)[0]
    self.m.gclient.c.revisions[first_solution_name] = str(
        bot_update_result.properties[rev_property])
    self._resolve_fixed_revisions(bot_update_result)

    self.ensure_checkout(patch=False,
                         no_fetch_tags=True,
                         update_presentation=False,
                         turboci_check_id=turboci_check_id)

  def step_name(self, patch, suffix):
    name = 'bot_update'
    if not patch:
      name += ' (without patch)'
    if suffix:
      name += f' - {suffix}'
    return name

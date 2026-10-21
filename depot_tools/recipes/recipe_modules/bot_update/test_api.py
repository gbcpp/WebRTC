# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import collections.abc
import hashlib
import json
import struct
import typing

from recipe_engine import recipe_test_api


class BotUpdateTestApi(recipe_test_api.RecipeTestApi):

  @recipe_test_api.mod_test_data
  @staticmethod
  def revisions(val: dict[str, str]):
    return val

  @recipe_test_api.mod_test_data
  @staticmethod
  def repo_urls(val: dict[str, str]):
    return val

  @recipe_test_api.mod_test_data
  @staticmethod
  def fail_checkout(val: bool):
    return val

  @recipe_test_api.mod_test_data
  @staticmethod
  def fail_patch(val: bool | typing.Literal['download']):
    return val

  @recipe_test_api.mod_test_data
  @staticmethod
  def commit_positions(val: bool):
    return val

  def output_json(
      self,
      *,
      first_sln: str | None = None,
      revisions: collections.abc.Mapping[str, str] | None = None,
      fixed_revisions: collections.abc.Mapping[str, str] | None = None,
      got_revision_mapping: collections.abc.Mapping[str, str] | None = None,
      repo_urls: collections.abc.Mapping[str, str] | None = None,
      patch_root: str | None = None,
      fail_checkout: bool = False,
      fail_patch: bool | typing.Literal['download'] = False,
      commit_positions: bool = True,
  ):
    """Synthesized json output for bot_update.py.

    Revision values will be replaced with generated values if they are
    equal to 'HEAD' or if they are a ref (starts with refs/ or origin/).

    Args:
      first_sln: The name of the first solution in the gclient config.
        This will apear in the resultant json's root value. If not
        provided, then the first project that appears in revisions will
        be used. An entry for this will appear in the resultant json's
        manifest even if it doesn't appear in revisions, fixed_revisions
        or got_revision_mapping.
      revisions: A mapping from project name/checkout-relative repo path
        to the revision that will appear in the manifests in the
        resultant json. Any projects present in fixed_revisions or
        got_revision_mapping will also result in entries in the
        manifests. If non-empty, the resultant json's root value will be
        the first project. An empty value for a project indicates to
        generate a revision. If first_sln isn't specified, then the
        first project will be used as first_sln. Dicts have a guaranteed
        iteration order based on declaration/insertion order, but other
        mappings may not, so they may produce inconsistent results if
        first_sln isn't specified.
      fixed_revisions: A mapping from project name/checkout-relative
        repo path to the revisions to be used for the project. The
        provided revisions will be reported as-is in the fixed_revisions
        of the resultant json. The resultant json's manifests will
        include entries for any project's not present in revisions. If
        non-empty and revisions is empty or None, the resultant json's
        root value will be the first project. It is an error if an entry
        exists for a project in revisions unless the values are equal,
        the value in revisions is empty or the value in fixed_revisions
        would be replaced with a generated value and the value in
        revisions would not be.
      got_revision_mapping: A mapping from property name to project
        name/checkout-relative repo path. The resultant json will have
        the given property set to the revision of that project. The
        resultant json's manifests will include entries for any projects
        not present in revisions. If non-empty and revisions and
        fixed_revisions are both empty or None, the resultant json's
        root value will be the first project.
      repo_urls: A mapping from project name/checkout-relative repo path
        to the repo URLs for the project. When constructing the
        manifests in the result json, the the provided URLs will be used
        for the repository values for those projects.
      patch_root: The relative path within the checkout to where the
        patch should be applied.
      fail_checkout: Whether or not the simulated checkout should fail.
      fail_patch: Whether or not the checkout should fail to apply the
        patch. A value of 'download' can be provided to indicate a
        failure to download the patch.
      commit_positions: Whether or not to generate commit position
        properties when generating revision properties. If true, any
        project that has a revision property generated will have another
        property generated with the same name with _cp appended with a
        commit position as the value.
    """
    t = recipe_test_api.StepTestData()

    output: dict[str, typing.Any] = {
        'did_run': True,
    }

    if fail_checkout:
      t.retcode = 1
    else:
      assert revisions or fixed_revisions or got_revision_mapping, (
          'a non-empty value must be provided for at least one of'
          ' revisions, fixed_revisions or got_revision_mapping')
      assert first_sln or revisions, (
          'a non-empty value must be provided for first_sln or revisions')

      revisions = revisions or {}
      first_sln = first_sln or next(iter(revisions))
      fixed_revisions = fixed_revisions or {}
      # If no got_revision_mapping is specified, then bot_update.py will set the
      # got_revision property for the first solution. It also has some default
      # properties mapped in GOT_REVISION_MAPPINGS that isn't handled here for
      # test data
      got_revision_mapping = got_revision_mapping or {'got_revision': first_sln}

      def resolve_revision(project_name, revision):
        if revision == 'HEAD':
          return self.gen_revision(project_name)
        if revision.startswith('refs/') or revision.startswith('origin/'):
          if ':' in revision:
            return revision.split(':', 1)[1]
          return self.gen_revision('{}@{}'.format(project_name, revision))
        return revision

      def choose_revision(project_name, revision):
        fixed_revision = (fixed_revisions or {}).get(project_name)
        assert fixed_revision is None or fixed_revision, (
            f'empty fixed_revision provided for {project_name}')
        match (revision, fixed_revision):
          case ('', _):
            return resolve_revision(project_name, fixed_revision or 'HEAD')
          case (_, None):
            return resolve_revision(project_name, revision)
          case (_, _) if (revision == fixed_revision
                          or revision == fixed_revision.split(':', 1)[-1]):
            return resolve_revision(project_name, revision)
          case _, _:

            def will_generate(rev):
              return (':' not in rev
                      and resolve_revision(project_name, rev) != rev)

            # If the revision and fixed_revision are different, then the fixed
            # revision must be HEAD or a ref and revision must not be and the
            # revision will be treated as the revision of the commit that HEAD
            # or the ref point at
            assert (
                will_generate(fixed_revision) and not will_generate(revision)
            ), f'{project_name} revision and fixed_revision are different'
            return revision

      resolved_revisions = {
          project_name: choose_revision(project_name, revision)
          for project_name, revision in revisions.items()
      }

      for project_name, fixed_revision in fixed_revisions.items():
        if project_name not in resolved_revisions:
          resolved_revisions[project_name] = resolve_revision(
              project_name, fixed_revision)

      resolved_revisions.setdefault(first_sln, self.gen_revision(first_sln))

      properties = {}
      for property_name, project_name in got_revision_mapping.items():
        if project_name not in resolved_revisions:
          resolved_revisions[project_name] = self.gen_revision(project_name)
        properties[property_name] = resolved_revisions[project_name]
        if commit_positions:
          fixed_revision = (fixed_revisions.get(project_name)
                            or revisions.get(project_name) or 'HEAD')
          if fixed_revision.startswith('origin/'):
            ref = fixed_revision.replace('origin/', 'refs/heads/', 1)
          elif fixed_revision.startswith('refs/'):
            ref = fixed_revision
          else:
            ref = 'refs/heads/main'
          ref = ref.split(':', 1)[0]
          properties[f'{property_name}_cp'] = '%s@{#%s}' % (
              ref, self.gen_commit_position(project_name))

      output.update({
          'patch_root': patch_root,
          'root': first_sln,
          'properties': properties,
          'step_text': 'Some step text'
      })

      repo_urls = dict(repo_urls or {})

      def get_repo_url(project_name):
        return repo_urls.setdefault(project_name,
                                    f'https://fake.org/{project_name}.git')

      output.update({
          'manifest': {
              project_name: {
                  'repository': get_repo_url(project_name),
                  'revision': revision,
              }
              for project_name, revision in sorted(resolved_revisions.items())
          }
      })

      output.update({
          'source_manifest': {
              'version': 0,
              'directories': {
                  project_name: {
                      'git_checkout': {
                          'repo_url': get_repo_url(project_name),
                          'revision': revision
                      }
                  }
                  for project_name, revision in sorted(
                      resolved_revisions.items())
              }
          }
      })

      if fixed_revisions:
        output['fixed_revisions'] = fixed_revisions

      if patch_root and fail_patch:
        output['patch_failure'] = True
        output['failed_patch_body'] = '\n'.join([
            'Downloading patch...',
            'Applying the patch...',
            'Patch: foo/bar.py',
            'Index: foo/bar.py',
            'diff --git a/foo/bar.py b/foo/bar.py',
            'index HASH..HASH MODE',
            '--- a/foo/bar.py',
            '+++ b/foo/bar.py',
            'context',
            '+something',
            '-something',
            'more context',
        ])
        output['patch_apply_return_code'] = 1
        if fail_patch == 'download':
          output['patch_apply_return_code'] = 3
          t.retcode = 87
        else:
          t.retcode = 88

    return t + self.m.json.output(output)

  @staticmethod
  def gen_revision(project):
    """Hash project to bogus deterministic git hash values."""
    h = hashlib.sha1(project.encode('utf-8'))
    return h.hexdigest()

  @staticmethod
  def gen_commit_position(project):
    """Hash project to bogus deterministic Cr-Commit-Position values."""
    h = hashlib.sha1(project.encode('utf-8'))
    return struct.unpack('!I', h.digest()[:4])[0] % 300000

  def post_check_output_json(self, step_name: str, custom_check_fn):
    """Perform a post check on the output json of a bot_update step.

    Args:
      step_name: The name of the bot_update step to check.
      custom_check_fn: A function taking 2 positional arguments: the
        "magic check" function provided by the recipe engine and the
        deserialized bot_update output json.
    """

    def perform_post_check(check, steps):
      bot_update_step = steps[step_name]
      output_json = json.loads(bot_update_step.logs['json.output'])
      custom_check_fn(check, output_json)

    return self.post_check(perform_post_check)

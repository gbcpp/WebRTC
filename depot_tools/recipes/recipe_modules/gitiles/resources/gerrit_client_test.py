import sys
import os
import unittest
from unittest import mock
import urllib.parse
import importlib.util
# Setup depot_tools path
# This test is assumed to be run from the root of depot_tools or with PYTHONPATH set.
# For this script, we'll try to find it relative to the script location.
DEPOT_TOOLS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, DEPOT_TOOLS)


# Load gerrit_client
# Since it's a resource, we load it manually to avoid package issues
def load_gerrit_client():
  resource_path = os.path.join(os.path.dirname(__file__), 'gerrit_client.py')
  spec = importlib.util.spec_from_file_location("gerrit_client", resource_path)
  module = importlib.util.module_from_spec(spec)
  # Mock gerrit_util to avoid network/auth
  sys.modules['gerrit_util'] = mock.MagicMock()
  spec.loader.exec_module(module)
  return module


class GerritClientTest(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.gerrit_client = load_gerrit_client()
    cls.gerrit_util = sys.modules['gerrit_util']

  def setUp(self):
    self.gerrit_util.CreateHttpConn.reset_mock()

  def test_gitiles_get_simple(self):
    parsed = urllib.parse.urlparse('https://host/p/ref')
    self.gerrit_client.gitiles_get(parsed, mock.MagicMock(), attempts=1)
    self.gerrit_util.CreateHttpConn.assert_called_with('host', '/p/ref')

  def test_gitiles_get_quoting_space(self):
    # Verify that spaces in path are quoted.
    parsed = urllib.parse.urlparse('https://host/p/path with spaces')
    self.gerrit_client.gitiles_get(parsed, mock.MagicMock(), attempts=1)
    self.gerrit_util.CreateHttpConn.assert_called_with(
        'host', '/p/path%20with%20spaces')

  def test_gitiles_get_quoting_plus(self):
    # Verify that + (special for Gitiles) is quoted in the path.
    parsed = urllib.parse.urlparse('https://host/repo/+log/master')
    self.gerrit_client.gitiles_get(parsed, mock.MagicMock(), attempts=1)
    self.gerrit_util.CreateHttpConn.assert_called_with('host',
                                                       '/repo/%2Blog/master')

  def test_gitiles_get_with_query(self):
    # Verify that query parameters are NOT broken by over-quoting.
    # This currently fails due to the bug in gerrit_client.py
    url = 'https://host/repo/+log/master?format=json&s=deadbeef'
    parsed = urllib.parse.urlparse(url)
    self.gerrit_client.gitiles_get(parsed, mock.MagicMock(), attempts=1)

    args, _ = self.gerrit_util.CreateHttpConn.call_args
    self.assertEqual(args[1], '/repo/%2Blog/master?format=json&s=deadbeef')


if __name__ == '__main__':
  unittest.main()

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

# Load the script with hyphens in name as a module
test_dir = os.path.dirname(os.path.abspath(__file__))
script_path = os.path.abspath(
    os.path.join(test_dir, "..", "gclient-new-workdir.py"))

# Ensure depot_tools root is in sys.path so gclient_utils can be imported
depot_tools_dir = os.path.dirname(script_path)
if depot_tools_dir not in sys.path:
    sys.path.insert(0, depot_tools_dir)

loader = importlib.machinery.SourceFileLoader(
    "gclient_new_workdir",
    script_path,
)
spec = importlib.util.spec_from_loader(loader.name, loader)
gclient_new_workdir = importlib.util.module_from_spec(spec)
loader.exec_module(gclient_new_workdir)


@unittest.skipIf(sys.platform == 'win32',
                 'gclient-new-workdir not supported on Windows')
class TestGclientNewWorkdir(unittest.TestCase):

    @patch("subprocess.check_output")
    @patch("os.stat")
    @patch("os.access")
    @patch("subprocess.check_call")
    @patch("os.makedirs")
    @patch("sys.exit")
    def test_abort_on_btrfs_fail(self, mock_exit, mock_makedirs,
                                 mock_check_call, mock_os_access, mock_os_stat,
                                 mock_check_output):
        # Setup mocks
        mock_check_output.return_value = b'btrfs'
        mock_stat_res = MagicMock()
        mock_stat_res.st_ino = 256
        mock_os_stat.return_value = mock_stat_res

        def mock_cc(args, **kwargs):
            _ = kwargs
            if len(args) > 2 and args[2] == 'snapshot':
                raise OSError("Failed")

        mock_check_call.side_effect = mock_cc

        # Make mock_exit raise SystemExit to stop execution
        mock_exit.side_effect = SystemExit(1)

        # Mock os.access to return True for diagnostics
        mock_os_access.return_value = True

        # Mock parse_options
        mock_args = MagicMock()
        mock_args.repository = "repo"
        mock_args.new_workdir = "dest"

        with patch.object(gclient_new_workdir,
                          "parse_options",
                          return_value=mock_args):
            try:
                gclient_new_workdir.main()
            except SystemExit:
                pass  # Expected

        # Assertions
        mock_exit.assert_called_with(1)
        mock_makedirs.assert_not_called()

    @patch("subprocess.check_output")
    @patch("os.stat")
    @patch("os.access")
    @patch("os.makedirs")
    @patch("sys.exit")
    @patch.object(gclient_new_workdir, "support_copy_on_write")
    def test_fallback_on_non_subvolume(self, mock_support_cow, mock_exit,
                                       mock_makedirs, mock_os_access,
                                       mock_os_stat, mock_check_output):
        # Setup mocks
        mock_check_output.return_value = b'btrfs'
        mock_stat_res = MagicMock()
        mock_stat_res.st_ino = 123  # Not subvolume!
        mock_os_stat.return_value = mock_stat_res

        # Mock os.access to return True for diagnostics
        mock_os_access.return_value = True

        # Mock support_copy_on_write to stop execution after os.makedirs
        mock_support_cow.side_effect = SystemExit(0)

        # Mock parse_options
        mock_args = MagicMock()
        mock_args.repository = "repo"
        mock_args.new_workdir = "dest"

        with patch.object(gclient_new_workdir,
                          "parse_options",
                          return_value=mock_args):
            try:
                gclient_new_workdir.main()
            except SystemExit:
                pass

        # Assertions
        mock_exit.assert_not_called()
        # It should proceed to os.makedirs with resolved path
        mock_makedirs.assert_called_with(os.path.realpath("dest"))

    @patch("subprocess.check_output")
    @patch("os.stat")
    @patch("os.access")
    @patch("subprocess.check_call")
    @patch("os.makedirs")
    @patch("sys.exit")
    @patch.object(gclient_new_workdir, "support_copy_on_write")
    def test_btrfs_snapshot_success(self, mock_support_cow, mock_exit,
                                    mock_makedirs, mock_check_call,
                                    mock_os_access, mock_os_stat,
                                    mock_check_output):
        # Setup mocks
        mock_check_output.return_value = b'btrfs'
        mock_stat_res = MagicMock()
        mock_stat_res.st_ino = 256
        mock_os_stat.return_value = mock_stat_res

        with patch.object(gclient_new_workdir,
                          "btrfs_subvol_snapshot",
                          return_value=True):
            mock_support_cow.side_effect = SystemExit(0)

            mock_args = MagicMock()
            mock_args.repository = "repo"
            mock_args.new_workdir = "dest"

            with patch.object(gclient_new_workdir,
                              "parse_options",
                              return_value=mock_args):
                try:
                    gclient_new_workdir.main()
                except SystemExit:
                    pass

        mock_makedirs.assert_not_called()

    @patch("subprocess.check_output")
    @patch("os.stat")
    @patch("os.access")
    @patch("subprocess.check_call")
    @patch("os.makedirs")
    @patch("sys.exit")
    def test_diagnostics_repo_not_readable(self, mock_exit, mock_makedirs,
                                           mock_check_call, mock_os_access,
                                           mock_os_stat, mock_check_output):
        # Setup mocks
        mock_check_output.return_value = b'btrfs'
        mock_stat_res = MagicMock()
        mock_stat_res.st_ino = 256
        mock_os_stat.return_value = mock_stat_res

        def mock_cc(args, **kwargs):
            _ = kwargs
            if args[2] == 'snapshot':
                raise OSError("Failed")

        mock_check_call.side_effect = mock_cc

        # Make mock_exit raise SystemExit to stop execution
        mock_exit.side_effect = SystemExit(1)

        # Mock os.access: False for repo (not readable)
        def side_effect(path, mode):
            if path == "repo" and mode == os.R_OK:
                return False
            return True

        mock_os_access.side_effect = side_effect

        # Mock parse_options
        mock_args = MagicMock()
        mock_args.repository = "repo"
        mock_args.new_workdir = "dest"

        with patch.object(gclient_new_workdir,
                          "parse_options",
                          return_value=mock_args):
            try:
                gclient_new_workdir.main()
            except SystemExit:
                pass

        # Assertions
        mock_exit.assert_called_with(1)
        mock_makedirs.assert_not_called()

    @patch("subprocess.check_output")
    @patch("os.stat")
    @patch("os.access")
    @patch("subprocess.check_call")
    @patch("os.makedirs")
    @patch("sys.exit")
    def test_diagnostics_dest_not_writable(self, mock_exit, mock_makedirs,
                                           mock_check_call, mock_os_access,
                                           mock_os_stat, mock_check_output):
        # Setup mocks
        mock_check_output.return_value = b'btrfs'
        mock_stat_res = MagicMock()
        mock_stat_res.st_ino = 256
        mock_os_stat.return_value = mock_stat_res

        def mock_cc(args, **kwargs):
            _ = kwargs
            if args[2] == 'snapshot':
                raise OSError("Failed")

        mock_check_call.side_effect = mock_cc

        # Make mock_exit raise SystemExit to stop execution
        mock_exit.side_effect = SystemExit(1)

        # Mock os.access: False for dest parent (not writable)
        def side_effect(path, mode):
            if path == "dir" and mode == os.W_OK:
                return False
            return True

        mock_os_access.side_effect = side_effect

        # Mock parse_options
        mock_args = MagicMock()
        mock_args.repository = "repo"
        mock_args.new_workdir = "dir/dest"

        with patch.object(gclient_new_workdir,
                          "parse_options",
                          return_value=mock_args):
            try:
                gclient_new_workdir.main()
            except SystemExit:
                pass

        # Assertions
        mock_exit.assert_called_with(1)
        mock_makedirs.assert_not_called()


    @patch("os.walk")
    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("os.symlink")
    @patch.object(gclient_new_workdir, "copy_on_write")
    @patch.object(gclient_new_workdir, "adopt_git_worktree")
    def test_main_detects_git_file(self, mock_adopt, mock_cow, mock_symlink,
                                   mock_makedirs, mock_exists, mock_walk):
        # Mock parse_options
        mock_args = MagicMock()
        mock_args.repository = "/fake/repo"
        mock_args.new_workdir = "/fake/dest"
        mock_args.copy_on_write = True
        mock_args.use_git_worktree = True
        mock_args.max_depth = None

        with patch.object(gclient_new_workdir,
                          "parse_options",
                          return_value=mock_args):
            # Mock os.walk to return a directory
            mock_walk.return_value = [("/fake/repo", ["dir1"], [])]

            # Mock os.path.exists
            def exists_side_effect(path):
                if path == "/fake/repo/.gclient":
                    return True
                if path == "/fake/dest/.gclient":
                    return False
                if path == "/fake/repo/.git":
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            # Mock is_btrfs_subvolume to return False
            with patch.object(gclient_new_workdir,
                              "is_btrfs_subvolume",
                              return_value=False):
                gclient_new_workdir.main()

            # Verify that adopt_git_worktree was called!
            mock_adopt.assert_called_once_with("/fake/repo", "/fake/dest")

if __name__ == "__main__":
    unittest.main()

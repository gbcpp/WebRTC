#!/usr/bin/env python3
# Copyright 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Usage:
#    gclient-new-workdir.py [options] <repository> <new_workdir>
#

import argparse
import ctypes
import ctypes.util
import os
import random
import shutil
import subprocess
import sys
import textwrap

import gclient_utils
import git_common


def parse_options():
    if sys.platform == 'win32':
        print(
            'ERROR: This script cannot run on Windows because it uses symlinks.'
        )
        sys.exit(1)
    if gclient_utils.IsEnvCog():
        print('ERROR: This script cannot run in non-git environment.')
        sys.exit(1)

    parser = argparse.ArgumentParser(description='''Clone an existing '''
    '''gclient workspace, taking care of all sub-repositories.''')
    parser.add_argument('repository',
                        type=os.path.abspath,
                        help='should contain a .gclient file')
    parser.add_argument('new_workdir', help='must not exist')
    parser.add_argument(
        '--use-git-worktree',
        action='store_true',
        default=True,
        help=
        '''Use git worktree instead of using symlinks for .git folders (default).''',
    )
    parser.add_argument(
        '--use-git-symlinks',
        action='store_false',
        dest='use_git_worktree',
        help='''Use symlinks for .git folders instead of using git worktree.''',
    )
    parser.add_argument(
        '--copy-on-write',
        action=argparse.BooleanOptionalAction,
        default=None,
        help='''Force use of a copy-on-write flag when copying for better '''
        '''performance and disk utilization. This is the default behavior on '''
        '''supported copy-on-write FS like btrfs, ZFS, or APFS.''')
    parser.add_argument('--reflink',
                        action=argparse.BooleanOptionalAction,
                        dest='copy_on_write',
                        help=argparse.SUPPRESS)
    parser.add_argument(
        '--max-depth',
        type=int,
        default=None,
        help='''Maximum depth to link git repositories. A value of 0 '''
        '''corresponds to the gclient workspace, a value of 1 corresponds to '''
        '''sub-directories of the workspace, and so on. A value of -1 means '''
        '''there is no limit. The default is 1 if copy-on-write is used, '''
        '''otherwise the default is -1.''')
    args = parser.parse_args()

    if '--use-git-worktree' not in sys.argv and '--use-git-symlinks' not in sys.argv:
        print(
            'Warning: --use-git-worktree is now the default. If you experience\n'
            'issues, you can use --use-git-symlinks and please file a bug:\n'
            'https://issues.chromium.org/u/0/issues/new?component=1456102',
            file=sys.stderr)

    if '--reflink' in sys.argv or '--no-reflink' in sys.argv:
        print(
            'Warning: --reflink and --no-reflink are deprecated. Use '
            '--copy-on-write or --no-copy-on-write instead.',
            file=sys.stderr)

    if not os.path.exists(args.repository):
        parser.error('Repository "%s" does not exist.' % args.repository)

    gclient = os.path.join(args.repository, '.gclient')
    if not os.path.exists(gclient):
        parser.error('No .gclient file at "%s".' % gclient)

    if os.path.exists(args.new_workdir):
        parser.error('New workdir "%s" already exists.' % args.new_workdir)

    return args


_libc = None


def clonefile_darwin(src, dst):
    global _libc
    if _libc is None:
        libc_path = ctypes.util.find_library('c')
        _libc = ctypes.CDLL(libc_path, use_errno=True)
        _libc.clonefile.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int
        ]
        _libc.clonefile.restype = ctypes.c_int
    # CLONE_NOFOLLOW (0x0001) | CLONE_ACL (0x0004) = 5
    res = _libc.clonefile(os.fsencode(src), os.fsencode(dst), 5)
    if res != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), src, None, dst)


def copy_on_write(src, dest):
    """Copies a file or directory using copy-on-write, if possible."""
    if sys.platform == 'darwin':
        clonefile_darwin(src, dest)
    else:
        subprocess.check_call(['cp', '-a', '--reflink', src, dest])


def support_copy_on_write(src, dest):
    # Use of a copy-on-write flag always succeeds when 'src' is a symlink or a directory
    assert os.path.isfile(src) and not os.path.islink(src)
    try:
        if sys.platform == 'darwin':
            clonefile_darwin(src, dest)
        else:
            subprocess.check_output(['cp', '-a', '--reflink', src, dest],
                                    stderr=subprocess.STDOUT)
    except OSError:
        # clonefile_darwin failed
        return False
    except subprocess.CalledProcessError:
        # cp --reflink failed
        return False
    finally:
        if os.path.isfile(dest):
            os.remove(dest)
    return True


def btrfs_subvol_snapshot(src, dest):
    """Creates a Btrfs snapshot of src at dest.
    Fails hard with detailed diagnostics if it fails."""
    try:
        subprocess.check_call(['btrfs', 'subvol', 'snapshot', src, dest],
                              stderr=subprocess.STDOUT)
    except (subprocess.CalledProcessError, OSError):
        print(f"Error: Failed to create Btrfs snapshot of '{src}'.")

        # Diagnostics
        readable = os.access(src, os.R_OK)
        parent_dest = os.path.dirname(dest)
        writable = os.access(parent_dest, os.W_OK)

        if not readable:
            print(
                f"  [✗] Permission denied: Source repository '{src}' is not readable by you."
            )
            print(
                "      Please ensure you have read permissions to the source subvolume."
            )

        if not writable:
            print(
                f"  [✗] Permission denied: Destination parent directory '{parent_dest}' is not writable by you."
            )
            print(
                "      Please ensure you have write permissions to the destination parent directory."
            )

        if readable and writable:
            print(
                "  [?] Permissions appear OK. The failure might be due to other Btrfs restrictions."
            )
            print(
                "      Consider checking if you have reached disk quota or if the filesystem is read-only."
            )

        return False
    assert os.path.exists(dest)
    return True


def is_btrfs_subvolume(path):
    """Returns True if the path is a valid Btrfs subvolume (root)."""
    try:
        # Check if filesystem is btrfs
        fstype = subprocess.check_output(
            ['findmnt', '-no', 'FSTYPE', '--target', path],
            stderr=subprocess.DEVNULL).decode().strip()
        if fstype != 'btrfs':
            return False
        # In Btrfs, the root of a subvolume always has inode 256.
        return os.stat(path).st_ino == 256
    except (subprocess.CalledProcessError, OSError):
        return False


def real_git_dir(repo_path):
    relative_git_dir = (
        subprocess.check_output(
            ['git', 'rev-parse', '--git-dir'], cwd=repo_path
        )
        .decode()
        .strip()
    )
    return os.path.realpath(os.path.join(repo_path, relative_git_dir))


def link_git_repo(src, dest, use_copy_on_write):
    print('Linking: %s/.git' % src)
    src_git_dir = real_git_dir(src)
    dest_git_dir = os.path.join(dest, '.git')
    git_common.make_workdir(src_git_dir, dest_git_dir)
    if use_copy_on_write:
        src_index = os.path.join(src_git_dir, 'index')
        dest_index = os.path.join(dest_git_dir, 'index')
        copy_on_write(src_index, dest_index)
        # Detach the HEAD ref without checking out files or updating the index.
        subprocess.check_call(
            ['git', 'update-ref', '--no-deref', 'HEAD', 'HEAD'], cwd=dest
        )
    else:
        print('Running: git checkout --detach -f %s' % dest)
        subprocess.check_call(['git', 'checkout', '--detach', '-f'], cwd=dest)


def adopt_git_worktree(src, dest):
    """Adopts an existing directory as a git worktree.

    Note that this function requires copy-on-write (reflink) support.
    """
    assert os.path.exists(dest)
    # Rename the existing directory since `git worktree add` won't work if the
    # worktree directory already exists even with the `--force` flag.
    tmp_dest = os.path.join(
        os.path.dirname(dest),
        'tmp-' + os.path.basename(dest) + '-' + '%08x' % random.getrandbits(32),
    )
    os.rename(dest, tmp_dest)
    # Run `git worktree add --no-checkout` to create the worktree without
    # touching any files in the worktree.
    print('Running: git worktree add %s --no-checkout -d -f' % dest)
    subprocess.check_call(
        ['git', 'worktree', 'add', dest, '--no-checkout', '-d', '-f'], cwd=src
    )
    # Move the .git file from the worktree to the temporary directory and move
    # the temporary directory back to the worktree directory. Note that the .git
    # file is different from the worktree's real .git directory used below.
    shutil.move(os.path.join(dest, '.git'), tmp_dest)
    shutil.rmtree(dest)
    os.rename(tmp_dest, dest)
    # Copy the index so that the worktree is aware of files in the repository.
    src_index = os.path.join(real_git_dir(src), 'index')
    dest_index = os.path.join(real_git_dir(dest), 'index')
    copy_on_write(src_index, dest_index)


def create_git_worktree(src, workdir):
    print('Running: git worktree add %s -d -f' % workdir)
    subprocess.check_call(
        ['git', 'worktree', 'add', workdir, '-d', '-f'], cwd=src
    )


def main():
    args = parse_options()

    args.repository = os.path.realpath(args.repository)
    args.new_workdir = os.path.realpath(args.new_workdir)

    if is_btrfs_subvolume(args.repository):
        if not btrfs_subvol_snapshot(args.repository, args.new_workdir):
            sys.exit(1)
        # If btrfs is being used, reflink support is always present, and there's
        # no benefit to not using it.
        args.copy_on_write = True
    else:
        os.makedirs(args.new_workdir)

    # If any of the operations below fail, we want to clean up the new workdir.
    try:
        gclient = os.path.join(args.repository, '.gclient')
        new_gclient = os.path.join(args.new_workdir, '.gclient')

        if args.copy_on_write is None:
            args.copy_on_write = support_copy_on_write(
                os.path.realpath(gclient), new_gclient)
            if args.copy_on_write:
                print('Copy-on-write support is detected.')

        if not os.path.exists(new_gclient):
            os.symlink(gclient, new_gclient)

        if args.max_depth is None:
            # Since we're doing a btrfs subvolume snapshot or reflink copy, the
            # sub-repositories will already be present in the copy, and we only
            # need to link the .git directory for the top-level repositories.
            args.max_depth = 1 if args.copy_on_write else -1

        visited_dirs = set()
        for root, dirs, _ in os.walk(args.repository, followlinks=True):
            # Keep track of visited directories to avoid processing the same
            # directory multiple times or infinite loops due to symlink cycles.
            root = os.path.realpath(root)
            if root in visited_dirs:
                dirs[:] = []
                continue
            visited_dirs.add(root)

            rel_path = os.path.relpath(root, args.repository)
            if rel_path == '.':
                current_depth = 0
            else:
                current_depth = rel_path.count(os.sep) + 1

            # Check if there's a .git directory before modifying dirs.
            has_git = os.path.exists(os.path.join(root, '.git'))
            # Don't descend into the .git directory.
            if '.git' in dirs:
                dirs.remove('.git')

            # If we've reached the max depth, remove all directories from the
            # list so that os.walk doesn't descend into them.
            if args.max_depth != -1 and current_depth >= args.max_depth:
                dirs[:] = []

            # If there's no .git directory, there's nothing to do.
            if not has_git:
                continue

            if rel_path == '.':
                workdir = args.new_workdir
            else:
                workdir = os.path.join(args.new_workdir, rel_path)

            if args.copy_on_write:
                if not os.path.exists(workdir):
                    print('Copying: %s' % workdir)
                    copy_on_write(root, workdir)
                workdir_git = os.path.join(workdir, '.git')
                if os.path.exists(workdir_git):
                    if os.path.isdir(workdir_git):
                        shutil.rmtree(workdir_git)
                    else:
                        os.remove(workdir_git)

            if args.use_git_worktree:
                if args.copy_on_write:
                    adopt_git_worktree(root, workdir)
                else:
                    create_git_worktree(root, workdir)
            else:
                link_git_repo(root,
                              workdir,
                              use_copy_on_write=args.copy_on_write)

        if args.copy_on_write:
            print(
                textwrap.dedent(
                    '''\
        The repo was copied using copy-on-write, and the artifacts were retained.
        More details on http://crbug.com/721585.

        Depending on your usage pattern, you might want to do "gn gen"
        on the output directories. More details: http://crbug.com/723856.'''
                )
            )
    except Exception as e:
        print(f'Error: {e}')
        print(f'Cleaning up {args.new_workdir}')
        if is_btrfs_subvolume(args.new_workdir):
            subprocess.check_call(
                ['btrfs', 'subvol', 'delete', args.new_workdir]
            )
        else:
            shutil.rmtree(args.new_workdir, ignore_errors=True)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())

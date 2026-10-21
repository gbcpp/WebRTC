# jj for depot-tools projects.
jj is a Git-compatible version control system.

This directory contains documentation and configuration to support jj for depot tools projects.

## Unsupported status of jj

jj is not officially supported for working with Chromium or any other projects that leverage depot_tools. The support that exists within depot_tools is community contributed and works on a best-effort and as-is basis. If something doesn't work in jj you're welcome to contribute a fix, or use git as the supported version control CLI.

There is no SLO for triage or fixing of bugs and no dedicated staffing responsible for jj.

## Contributing

To contribute, you can either go one of three routes:
* For config changes, just edit this directory's `config_template.toml`  file directly. However, we don't currently have a mechanism to get this to downstream projects automatically. If you're a copybara expert, you could choose to configure this for your repo.
* For new features, the preferred approach is to contribute directly to [upstream jj](https://github.com/jj-vcs/jj).
* If that is not feasible, writing scripts in this directory is possible, but should be avoided if it can be done upstream.

## Issues
To report issues, use [go/jj-oss-bug](https://b.corp.google.com/issues/new?component=1987440&template=2234928).

## Getting started
1.  Join [the mailing list](https://groups.google.com/g/chromium-jj-users). This
    is very important, as this is how we will communicate important information.
    Note that this is not an official group.
2.  Follow go/jj-in-chromium (only currently open to googlers). Further
    instructions will be added later which also support external contributors.
3.  Optional: Try the
    [official jj tutorial](https://jj-vcs.github.io/jj/prerelease/tutorial/) or
    [the unofficial one](https://steveklabnik.github.io/jujutsu-tutorial/)

## Using jj for depot-tools based projects.
### Working with commits
Most commands for working locally with commits work just fine. The one
exception to this is that Git submodules are not yet supported by jj.

This means whenever you see jj say "ignoring git submodule" (generally only
when you switch between submitted commits), you will need to run `gclient sync`.


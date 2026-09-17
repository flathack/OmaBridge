# Installer security

The supported entry point is `./scripts/install.sh`. Running it explicitly requests
installation of the companion app, launcher, desktop entry, icon and bar widget,
and activation through Omarchy. It does not require root.

The entry point uses `/bin/bash -p`, so Bash startup files and imported shell
functions cannot run before the installer. It then starts `/usr/bin/python3 -I`
through `/usr/bin/env -i` with a minimal environment. `PATH` is fixed to
`/usr/bin:/bin`; Omarchy commands are resolved to root-owned, non-writable
executables and invoked by their absolute paths. Only the desktop-session values
needed to talk to the current Omarchy shell, the XDG destination paths and the
documented HTTP(S) proxy variables are retained. Python, loader, pip, CA,
`OMARCHY_PATH`, startup-shell and arbitrary tool variables are removed. The
Python installer repeats this allowlist for every child process.

## Immutable downloaded code

`requirements/install.lock` pins every runtime and build dependency, including
pip, setuptools, wheel and packaging, to an exact version and committed SHA-256
wheel hashes. There is no automatic lock regeneration or fallback to source
packages. The supported target is standard CPython 3.11–3.14 on Linux x86_64/aarch64
with compatible manylinux system libraries. Unsupported targets fail rather than
building an unreviewed source distribution.

The installed OS Python and its bundled `venv`/`ensurepip` are the bootstrap trust
base. A fresh environment first downloads with `--require-hashes` and
`--only-binary=:all:`. It then installs the locked artifacts with the same checks
and `--no-index`. Pip configuration/environment overrides are disabled. The local
OmaBridge source is built using the locked backend with `--no-build-isolation`,
`--no-deps` and `--no-index`, and installed without dependency resolution. The
locally built app comes from the submitted source; it is not another remote input.

A changed lock requires a new reviewed commit. When updating dependencies, select
exact versions, include all transitive wheels and their SHA-256 hashes from the
exact PyPI releases, and run `python3 -I scripts/check-install.py` plus CI on both
supported Python endpoints. The installer never regenerates hashes from downloads.
Hashes bind artifacts; they do not establish that upstream package code is safe.

## Destination ownership and writes

Each installation creates a new private environment under
`~/.local/share/omabridge/managed/install-*/venv`. Existing environments, including
legacy `omabridge/venv`, are neither executed nor changed. They are retained for
running sessions. The launcher switches to the new environment only after the
locked build and import/dependency checks succeed.

The managed directory must be owned by the current user with mode `0700`. Existing
managed directories require a valid ownership receipt. The receipt stores installed
file hashes with mode `0600`. Pre-existing launcher, desktop, icon and widget files
must match that receipt, exact known historical OmaBridge bytes, or the current
repository asset. A matching plugin name or manifest ID alone is insufficient.
`scripts/legacy-install-hashes.json` records hashes from repository history through
`8aca5a5b0fafe01a3ecdfbbe11320a4a4217adba`; the old launcher/desktop templates are
compared byte-for-byte with the configured paths. Unknown or edited files abort
the installation. There is no force-overwrite option.

Path components are opened with `O_DIRECTORY|O_NOFOLLOW` and anchored by directory
file descriptors. Symlink components, unsafe ownership/write permissions, nonregular
files and hardlinks are rejected. All targets are rechecked after building and
immediately before each write. Replacements use an fsynced temporary file and atomic
rename; new files use a no-clobber hard link. A renamed or substituted parent is
rejected, and destination symlinks are never followed. Receipt updates retain old
and new hashes during publication so interrupted installations can recover.

The installer validates and backs up `shell.json`, then asks Omarchy to enable the
widget through its own CLI. It no longer rewrites shared bar configuration or moves
entire legacy plugin directories. An old `local.omabridge` entry can be disabled
explicitly with `omarchy plugin disable local.omabridge`.

This protects against collisions, unsafe path layouts and detected substitutions.
A hostile process controlling the same Linux account, the OS Python or Omarchy
itself is outside the boundary. Atomic publication is per file, not a transaction
spanning every installed file. If interrupted, rerun after resolving any reported
conflict; never delete unfamiliar files just to bypass a refusal.

## Validation

`tests/test_installer.py` covers known and foreign files, symlinks, hardlinks, FIFOs,
unsafe directories, parent/leaf substitution, no-clobber creation, legacy upgrades,
pip environment isolation and rejection of a tampered wheel. The isolated full
installation in `scripts/check-install.py` is also run in CI with Python 3.11 and
3.14. It performs actual locked downloads/builds without changing the real desktop.

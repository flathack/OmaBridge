"""User-local installer: locked wheels and fail-closed, owned destination writes."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
import uuid
import venv

PLUGIN_ID = 'io.github.flathack.omabridge'
RECEIPT = 'ownership.json'
MAX_FILE = 16 * 1024 * 1024


class InstallError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def absolute(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or any(c in str(path) for c in '\n\r\0'):
        raise InstallError(f'Expected an absolute path without traversal: {path}')
    return path


class Directory:
    """Anchor writes to checked directory descriptors; never traverse symlinks."""
    def __init__(self, path, create=False):
        self.path = absolute(path)
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in self.path.parts[1:]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
                info = os.fstat(fd)
                # A root-owned sticky ancestor (e.g. /tmp in tests) is safe to
                # traverse; every child is opened and checked independently.
                sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
                if info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022 and not sticky_root):
                    raise InstallError(f'Unsafe directory ownership or permissions: {self.path}')
            self.fd = fd
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        os.close(self.fd)

    def unchanged(self):
        with Directory(self.path) as current:
            before, after = os.fstat(self.fd), os.fstat(current.fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise InstallError(f'Directory changed during installation: {self.path}')

    def read(self, name):
        self.unchanged()
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or info.st_mode & 0o022 or info.st_size > MAX_FILE):
                raise InstallError(f'Unsafe existing file: {self.path / name}')
            data = stream.read(MAX_FILE + 1)
            after = os.fstat(stream.fileno())
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if len(data) > MAX_FILE or identity(info) != identity(after):
                raise InstallError(f'File changed during inspection: {self.path / name}')
            return (identity(info), digest(data), data)

    def write(self, name, data, expected, mode=0o644):
        self.unchanged()
        temporary = '.omabridge-' + uuid.uuid4().hex
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     mode=0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(data)
                os.fchmod(output.fileno(), mode)
                output.flush()
                os.fsync(output.fileno())
            if self.read(name) != expected:
                raise InstallError(f'Destination changed during installation: {self.path / name}')
            if expected is None:
                # link is no-clobber if another file appeared after inspection.
                os.link(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
            else:
                # rename replaces the entry itself; it never follows a target
                # symlink. Same-UID hostile processes are outside this boundary.
                os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass


def desktop_entry(launcher):
    executable = str(launcher).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    return ('[Desktop Entry]\nType=Application\nName=OmaBridge\nComment=Citrix sites for Omarchy\n'
            'Comment[de]=Citrix-Sites für Omarchy\nExec="' + executable + '"\nIcon=omabridge\n'
            'Terminal=false\nCategories=Network;RemoteAccess;\nStartupWMClass=omabridge\n').encode()


def read_receipt(directory):
    record = directory.read(RECEIPT)
    if record is None:
        raise InstallError(f'Unrecognized managed directory: {directory.path}')
    payload = json.loads(record[2])
    if (not isinstance(payload, dict) or payload.get('schema') != 1
            or payload.get('plugin') != PLUGIN_ID or not isinstance(payload.get('files'), dict)):
        raise InstallError('Invalid OmaBridge ownership receipt')
    for path, hashes in payload['files'].items():
        absolute(path)
        if not isinstance(hashes, list) or not all(isinstance(h, str) and len(h) == 64 for h in hashes):
            raise InstallError('Invalid OmaBridge ownership hashes')
    return payload


def save_receipt(directory, payload):
    data = (json.dumps(payload, indent=2, sort_keys=True) + '\n').encode()
    directory.write(RECEIPT, data, directory.read(RECEIPT), mode=0o600)


def pip_environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PIP_', 'PYTHON'))}
    # Suppress global/user pip configuration as well as environment overrides.
    env['PIP_CONFIG_FILE'] = os.devnull
    return env


def build_environment(generation, project):
    """Only downloaded wheels from the committed hash lock may execute."""
    environment = generation / 'venv'
    venv.EnvBuilder(with_pip=True, symlinks=False).create(environment)
    python = environment / 'bin/python'
    pip = [str(python), '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check', '--no-cache-dir']
    env = pip_environment()
    wheelhouse = generation / 'wheels'
    wheelhouse.mkdir(mode=0o700)
    lock = project / 'requirements/install.lock'
    subprocess.run(pip + ['download', '--require-hashes', '--only-binary=:all:',
                         '--index-url', 'https://pypi.org/simple', '-r', str(lock),
                         '--dest', str(wheelhouse)], check=True, env=env)
    subprocess.run(pip + ['install', '--force-reinstall', '--require-hashes', '--only-binary=:all:',
                         '--no-index', '--find-links', str(wheelhouse), '-r', str(lock)], check=True, env=env)
    # Build the submitted source with the locked backend, without an isolated
    # build environment or dependency resolution that could fetch more code.
    source = generation / 'source'
    source.mkdir(mode=0o700)
    for name in ['pyproject.toml', 'README.md', 'LICENSE']:
        shutil.copyfile(project / name, source / name)
    shutil.copytree(project / 'src/omabridge', source / 'src/omabridge', ignore=shutil.ignore_patterns('__pycache__'))
    output = generation / 'app-wheel'
    subprocess.run(pip + ['wheel', '--no-index', '--no-deps', '--no-build-isolation',
                         '--wheel-dir', str(output), str(source)], check=True, env=env)
    wheel, = output.glob('omabridge-*.whl')
    subprocess.run(pip + ['install', '--no-index', '--no-deps', str(wheel)], check=True, env=env)
    subprocess.run(pip + ['check'], check=True, env=env)
    subprocess.run([str(python), '-I', '-c', 'import omabridge, secretstorage; from PySide6 import QtWebEngineWidgets; print("Built OmaBridge", omabridge.__version__)'], check=True, env=env)
    # These are private, freshly-created staging directories, never old installs.
    for directory in [wheelhouse, source, output]:
        shutil.rmtree(directory)
    return python


def install(project, home, data, config, builder=build_environment, activate=True):
    home, data, config = map(absolute, (home, data, config))
    managed_path = data / 'omabridge/managed'
    launcher = home / '.local/bin/omabridge'
    legacy = json.loads((project / 'scripts/legacy-install-hashes.json').read_text())
    old_launcher = ('#!/bin/sh\nexec ' + shlex.quote(str(data / 'omabridge/venv/bin/omabridge')) + ' "$@"\n').encode()
    files = [
        (launcher, None, {digest(old_launcher)}, 0o755),
        (data / 'applications/omabridge.desktop', desktop_entry(launcher), {digest(desktop_entry(launcher))}, 0o644),
        (data / 'icons/hicolor/scalable/apps/omabridge.svg', (project / 'src/omabridge/assets/omabridge.svg').read_bytes(), set(legacy['src/omabridge/assets/omabridge.svg']), 0o644),
        (config / 'omarchy/plugins' / PLUGIN_ID / 'manifest.json', (project / 'manifest.json').read_bytes(), set(legacy['manifest.json']), 0o644),
        (config / 'omarchy/plugins' / PLUGIN_ID / 'BarWidget.qml', (project / 'BarWidget.qml').read_bytes(), set(legacy['BarWidget.qml']), 0o644),
    ]
    with contextlib.ExitStack() as stack:
        root = stack.enter_context(Directory(managed_path.parent, create=True))
        try:
            os.mkdir('managed', mode=0o700, dir_fd=root.fd)
            fresh = True
        except FileExistsError:
            fresh = False
        managed = stack.enter_context(Directory(managed_path))
        info = os.fstat(managed.fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise InstallError(f'Unsafe managed directory: {managed_path}')
        fcntl.flock(managed.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        payload = {'schema': 1, 'plugin': PLUGIN_ID, 'files': {}} if fresh else read_receipt(managed)
        if fresh:
            save_receipt(managed, payload)
        planned = []
        for path, content, known, mode in files:
            directory = stack.enter_context(Directory(path.parent, create=True))
            existing = directory.read(path.name)
            # Current repository assets and the previous receipt also establish
            # ownership; merely declaring our ID in a foreign file never does.
            if content is not None:
                known.add(digest(content))
            known.update(payload['files'].get(str(path), []))
            if existing is not None and existing[1] not in known:
                raise InstallError(f'Not an unmodified OmaBridge file; refusing to overwrite: {path}')
            planned.append([directory, path.name, content, mode, existing])
        # Omarchy owns shell.json. Check it before delegating its documented
        # enable operation, and never rewrite or migrate the shared file ourselves.
        shell_directory = stack.enter_context(Directory(config / 'omarchy', create=True))
        shell_config = shell_directory.read('shell.json')
        generation = managed_path / ('install-' + uuid.uuid4().hex)
        os.mkdir(generation.name, mode=0o700, dir_fd=managed.fd)
        python = builder(generation, project)
        managed.unchanged()
        planned[0][2] = ('#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' -I -m omabridge "$@"\n').encode()
        # Inspect every target again before the first change, after lengthy downloads.
        for directory, name, content, mode, existing in planned:
            if directory.read(name) != existing:
                raise InstallError(f'Destination changed during installation: {directory.path / name}')
        if shell_directory.read('shell.json') != shell_config:
            raise InstallError('Omarchy configuration changed during installation; please retry.')
        # Authorize both old and new hashes before replacement, allowing safe
        # recovery if power is lost between publishing a file and the final receipt.
        for directory, name, content, mode, existing in planned:
            payload['files'][str(directory.path / name)] = sorted({digest(content)} | ({existing[1]} if existing else set()))
        save_receipt(managed, payload)
        for directory, name, content, mode, existing in planned:
            directory.write(name, content, existing, mode)
            payload['files'][str(directory.path / name)] = [digest(content)]
        save_receipt(managed, payload)
        if activate:
            # Keep a private recovery copy before requesting the bar change.
            if shell_config is not None:
                managed.write('shell-backup-' + uuid.uuid4().hex + '.json', shell_config[2], None, mode=0o600)
            shell_directory.read('shell.json')
            subprocess.run(['omarchy-shell', 'shell', 'rescanPlugins'], check=True)
            for attempt in range(25):
                result = subprocess.run(['omarchy', 'plugin', 'enable', PLUGIN_ID], capture_output=True, text=True)
                if result.returncode == 0:
                    print(result.stdout.strip())
                    break
                if 'is not known' not in result.stderr or attempt == 24:
                    raise InstallError(result.stderr.strip() or 'Could not enable OmaBridge')
                time.sleep(.2)
        print('OmaBridge installed. Click Citrix in the bar to add a site.')


def main():
    if (sys.platform != 'linux' or platform.python_implementation() != 'CPython'
            or not (3, 11) <= sys.version_info[:2] <= (3, 14)
            or platform.machine() not in ('x86_64', 'aarch64') or sysconfig.get_config_var('Py_GIL_DISABLED')):
        raise InstallError('Requires Linux x86_64/aarch64 and CPython 3.11–3.14 (standard GIL build).')
    if os.getuid() == 0:
        raise InstallError('Run the installer as your desktop user, not root.')
    if not shutil.which('omarchy') or not shutil.which('omarchy-shell'):
        raise InstallError('The Omarchy Shell is required.')
    os.umask(0o077)
    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='omabridge-validate-') as temporary:
        for name in ['manifest.json', 'BarWidget.qml']:
            shutil.copyfile(project / name, Path(temporary) / name)
        subprocess.run(['omarchy', 'plugin', 'validate', temporary], check=True)
    home = Path.home()
    install(project, home, Path(os.environ.get('XDG_DATA_HOME', home / '.local/share')),
            Path(os.environ.get('XDG_CONFIG_HOME', home / '.config')))


if __name__ == '__main__':
    try:
        main()
    except (InstallError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Installation stopped: ' + str(error), file=sys.stderr)
        sys.exit(1)

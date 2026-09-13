"""Installer regression tests use isolated homes and no real credentials."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('omabridge_installer', PROJECT / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def targets(tmp_path):
    home = tmp_path / 'home'
    home.mkdir(mode=0o700)
    return home, home / '.local/share', home / '.config'


def fake_build(generation, project):
    python = generation / 'venv/bin/python'
    python.parent.mkdir(parents=True)
    python.write_text('demo executable')
    return python


def run_install(targets, builder=fake_build):
    installer.install(PROJECT, *targets, builder=builder, activate=False)


def test_fresh_install_and_owned_upgrade_preserve_other_files(targets):
    home, data, config = targets
    run_install(targets)
    launcher = home / '.local/bin/omabridge'
    first = launcher.read_bytes()
    receipt = data / 'omabridge/managed/ownership.json'
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert len(json.loads(receipt.read_text())['files']) == 5
    unrelated = config / 'omarchy/plugins' / installer.PLUGIN_ID / 'custom.txt'
    unrelated.write_text('leave alone')
    run_install(targets)
    assert launcher.read_bytes() != first
    assert unrelated.read_text() == 'leave alone'
    assert len(list((data / 'omabridge/managed').glob('install-*'))) == 2


@pytest.mark.parametrize('target', ['launcher', 'desktop', 'icon', 'manifest', 'widget'])
def test_foreign_destinations_abort_before_build(targets, target):
    home, data, config = targets
    paths = {'launcher': home / '.local/bin/omabridge',
             'desktop': data / 'applications/omabridge.desktop',
             'icon': data / 'icons/hicolor/scalable/apps/omabridge.svg',
             'manifest': config / 'omarchy/plugins' / installer.PLUGIN_ID / 'manifest.json',
             'widget': config / 'omarchy/plugins' / installer.PLUGIN_ID / 'BarWidget.qml'}
    path = paths[target]
    path.parent.mkdir(parents=True)
    path.write_text('unrelated user data')
    with pytest.raises(installer.InstallError, match='refusing to overwrite'):
        run_install(targets, lambda *args: pytest.fail('must reject before building'))
    assert path.read_text() == 'unrelated user data'


@pytest.mark.parametrize('kind', ['leaf_symlink', 'parent_symlink', 'hardlink', 'fifo', 'writable_parent', 'unmarked_managed'])
def test_unsafe_paths_are_rejected_without_touching_target(targets, kind):
    home, data, config = targets
    outside = home / 'outside'
    outside.mkdir()
    victim = outside / 'omabridge'
    victim.write_text('keep')
    directory = home / '.local/bin'
    directory.parent.mkdir(parents=True)
    if kind == 'parent_symlink':
        directory.symlink_to(outside)
    else:
        directory.mkdir()
        destination = directory / 'omabridge'
        if kind == 'leaf_symlink':
            destination.symlink_to(victim)
        elif kind == 'hardlink':
            os.link(victim, destination)
        elif kind == 'fifo':
            os.mkfifo(destination)
        elif kind == 'writable_parent':
            directory.chmod(0o777)
        else:
            (data / 'omabridge/managed').mkdir(parents=True, mode=0o700)
    with pytest.raises((installer.InstallError, OSError)):
        run_install(targets, lambda *args: pytest.fail('must reject before building'))
    assert victim.read_text() == 'keep'


def test_changed_target_during_build_aborts_all_publication(targets):
    home, data, config = targets
    run_install(targets)
    launcher = home / '.local/bin/omabridge'
    original = launcher.read_bytes()
    desktop = data / 'applications/omabridge.desktop'
    def substitute(generation, project):
        desktop.write_text('changed while downloading')
        return fake_build(generation, project)
    with pytest.raises(installer.InstallError, match='changed during installation'):
        run_install(targets, substitute)
    assert launcher.read_bytes() == original
    assert desktop.read_text() == 'changed while downloading'


def test_parent_substitution_does_not_write_into_replacement(targets):
    home, data, config = targets
    run_install(targets)
    directory = home / '.local/bin'
    def substitute(generation, project):
        directory.rename(home / 'original-bin')
        directory.mkdir()
        return fake_build(generation, project)
    with pytest.raises(installer.InstallError, match='Directory changed'):
        run_install(targets, substitute)
    assert not (directory / 'omabridge').exists()


def test_legacy_files_must_match_known_bytes_and_old_environment_is_not_executed(targets):
    home, data, config = targets
    launcher = home / '.local/bin/omabridge'
    launcher.parent.mkdir(parents=True)
    legacy = data / 'omabridge/venv/bin/omabridge'
    legacy.parent.mkdir(parents=True)
    legacy.write_text('must remain untouched')
    launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(str(legacy)) + ' "$@"\n')
    run_install(targets)
    assert legacy.read_text() == 'must remain untouched'
    assert '/managed/install-' in launcher.read_text()


def test_atomic_creation_does_not_clobber_a_racing_file(tmp_path, monkeypatch):
    with installer.Directory(tmp_path) as directory:
        real_link = os.link
        def race(source, destination, **kwargs):
            (tmp_path / destination).write_text('racing file')
            return real_link(source, destination, **kwargs)
        monkeypatch.setattr(os, 'link', race)
        with pytest.raises(FileExistsError):
            directory.write('new', b'new data', None)
    assert (tmp_path / 'new').read_text() == 'racing file'
    assert not list(tmp_path.glob('.omabridge-*'))


def test_pip_configuration_is_not_inherited(monkeypatch):
    monkeypatch.setenv('PIP_EXTRA_INDEX_URL', 'https://untrusted.invalid')
    monkeypatch.setenv('PIP_FIND_LINKS', '/untrusted')
    monkeypatch.setenv('PYTHONPATH', '/untrusted')
    env = installer.pip_environment()
    assert env['PIP_CONFIG_FILE'] == os.devnull
    assert 'PIP_EXTRA_INDEX_URL' not in env and 'PIP_FIND_LINKS' not in env
    assert 'PYTHONPATH' not in env


def test_lock_covers_runtime_backend_and_transitive_packages():
    logical = (PROJECT / 'requirements/install.lock').read_text().replace('\\\n', '')
    requirements = {}
    for line in logical.splitlines():
        if not line or line.startswith('#'):
            continue
        package, *hashes = line.split()
        name, version = package.split('==')
        assert hashes and all(h.startswith('--hash=sha256:') and len(h.split(':')[1]) == 64 for h in hashes)
        requirements[name.lower()] = version
    metadata = tomllib.loads((PROJECT / 'pyproject.toml').read_text())
    for requirement in metadata['build-system']['requires'] + metadata['project']['dependencies']:
        name, version = requirement.split('==')
        assert requirements[name.lower()] == version
    assert set(requirements) == {'pip', 'setuptools', 'wheel', 'packaging', 'pyside6', 'pyside6_addons',
                                'pyside6_essentials', 'shiboken6', 'secretstorage', 'cryptography',
                                'cffi', 'jeepney', 'pycparser'}


def test_tampered_wheel_is_rejected_before_installation(tmp_path):
    # Pip checks bytes before trying to open this deliberately invalid wheel.
    wheel = tmp_path / 'demo_pkg-1.0-py3-none-any.whl'
    wheel.write_bytes(b'tampered artifact')
    lock = tmp_path / 'bad.lock'
    lock.write_text('demo-pkg==1.0 --hash=sha256:' + '0' * 64 + '\n')
    result = subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
                             'download', '--no-index', '--require-hashes', '--only-binary=:all:',
                             '--find-links', str(tmp_path), '-r', str(lock), '--dest', str(tmp_path / 'out')],
                            env=installer.pip_environment(), capture_output=True, text=True)
    assert result.returncode != 0
    assert 'DO NOT MATCH THE HASHES' in result.stderr
    assert not list((tmp_path / 'out').glob('*.whl'))

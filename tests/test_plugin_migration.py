import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('plugin_migration', Path(__file__).parents[1] / 'scripts/migrate-plugin.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_migration_preserves_layout_settings_and_backup(tmp_path):
    config_dir, data_dir = tmp_path / 'config', tmp_path / 'data'
    old = config_dir / 'omarchy/plugins' / migration.OLD_ID
    old.mkdir(parents=True)
    (old / 'BarWidget.qml').write_text('demo custom widget')
    config = config_dir / 'omarchy/shell.json'
    original = {'bar': {'layout': {'right': [{'id': 'other.widget'}, {'id': migration.OLD_ID, 'custom': 42}]}},
                'disabledPlugins': [migration.OLD_ID], 'idle': {'lock': 300}}
    config.write_text(json.dumps(original))
    migration.migrate(config_dir, data_dir)
    updated = json.loads(config.read_text())
    assert updated['bar']['layout']['right'] == [{'id': 'other.widget'}, {'id': migration.NEW_ID, 'custom': 42}]
    assert updated['disabledPlugins'] == [migration.NEW_ID]
    assert updated['idle'] == original['idle']
    backup, = data_dir.glob('plugin-id-backup-*')
    assert json.loads((backup / 'shell.json').read_text()) == original
    assert (backup / migration.OLD_ID / 'BarWidget.qml').read_text() == 'demo custom widget'
    assert not old.exists()
    migration.migrate(config_dir, data_dir)
    assert list(data_dir.glob('plugin-id-backup-*')) == [backup]


def test_fresh_install_does_not_create_a_shell_config(tmp_path):
    migration.migrate(tmp_path / 'config', tmp_path / 'data')
    assert not (tmp_path / 'config').exists()
    assert not (tmp_path / 'data').exists()

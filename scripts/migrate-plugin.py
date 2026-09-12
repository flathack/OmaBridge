"""Migrate the development plugin ID without resetting the user's bar layout."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

OLD_ID = 'local.omabridge'
NEW_ID = 'io.github.flathack.omabridge'


def replace_id(value):
    if isinstance(value, dict):
        return {key: replace_id(item) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_id(item) for item in value]
    return NEW_ID if value == OLD_ID else value


def migrate(config_dir, data_dir):
    config = config_dir / 'omarchy/shell.json'
    old_plugin = config_dir / 'omarchy/plugins' / OLD_ID
    original = json.loads(config.read_text()) if config.exists() else {}
    updated = replace_id(original)
    if updated == original and not old_plugin.exists():
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='plugin-id-backup-', dir=data_dir))
    if config.exists():
        shutil.copy2(config, backup / 'shell.json')
    if updated != original:
        fd, temporary = tempfile.mkstemp(prefix='.shell-migrate-', dir=config.parent)
        try:
            with os.fdopen(fd, 'w') as output:
                json.dump(updated, output, indent=2, ensure_ascii=False)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            shutil.copymode(config, temporary)
            os.replace(temporary, config)
        finally:
            Path(temporary).unlink(missing_ok=True)
    if old_plugin.exists():
        shutil.move(str(old_plugin), str(backup / OLD_ID))
    print('Plugin ID migrated; backup: ' + str(backup))


if __name__ == '__main__':
    migrate(Path(sys.argv[1]), Path(sys.argv[2]))

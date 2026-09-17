"""Exercise a complete locked installation in a disposable home, without bar changes."""
import importlib.util
from pathlib import Path
import tempfile

project = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('omabridge_installer', project / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
installer.secure_environment()

with tempfile.TemporaryDirectory(prefix='omabridge-install-check-') as temporary:
    home = Path(temporary) / 'home'
    home.mkdir(mode=0o700)
    installer.install(project, home, home / '.local/share', home / '.config', activate=False)
    print('Fresh locked installation passed in an isolated home.')

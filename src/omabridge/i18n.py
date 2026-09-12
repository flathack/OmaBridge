"""Small English-source translation catalog, shared by the GUI and CLI."""
import json
from importlib.resources import files

GERMAN = json.loads(files('omabridge').joinpath('assets/de.json').read_text(encoding='utf-8'))
ENGLISH = {translated: source for source, translated in GERMAN.items()}
_language = 'en'


def language() -> str:
    return _language


def set_language(value: str):
    global _language
    if value not in {'en', 'de'}:
        raise ValueError('Unsupported language.')
    _language = value


def tr(source: str, **values) -> str:
    text = GERMAN.get(source, source) if _language == 'de' else source
    return text.format(**values) if values else text


def retranslate(text: str) -> str:
    """Refresh previously emitted application messages; never translate portal content."""
    return tr(ENGLISH.get(text, text))


def apply_qt_language():
    """Translate Qt-owned controls and WebEngine context menus on the GUI thread."""
    from PySide6.QtCore import QCoreApplication, QLibraryInfo, QTranslator
    app = QCoreApplication.instance()
    if app is None:
        return
    for translator in getattr(app, '_omabridge_translators', []):
        app.removeTranslator(translator)
        translator.deleteLater()
    app._omabridge_translators = []
    if _language == 'de':
        directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        for catalog in ('qtbase_de', 'qtwebengine_de'):
            translator = QTranslator(app)
            if translator.load(catalog, directory):
                app.installTranslator(translator)
                app._omabridge_translators.append(translator)
            else:
                translator.deleteLater()

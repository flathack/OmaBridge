"""Optional integration check against the installed Omarchy/Quickshell UI kit."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(not shutil.which('quickshell') or not Path('/usr/share/omarchy/shell/Ui').exists(),
                    reason='Requires the installed Omarchy UI kit and Quickshell')
def test_polling_does_not_change_popup_layout_or_erase_input(tmp_path):
    for name in ['Ui', 'Commons']:
        (tmp_path / name).symlink_to(Path('/usr/share/omarchy/shell') / name, target_is_directory=True)
    launcher = tmp_path / 'state'
    launcher.write_text('#!' + sys.executable + '\nimport json,time\ntime.sleep(.2)\nprint(json.dumps({"language":"en","locked":True,"sites":[]}))\n')
    launcher.chmod(0o700)
    code = Path('BarWidget.qml').read_text()
    code = code.replace('readonly property string launcher: Quickshell.env("HOME") + "/.local/bin/omabridge"',
                        'readonly property string launcher: ' + repr(str(launcher)))
    code = code.replace('    id: root', '''    id: root
    property alias testInput: passwordInput
    property alias testHint: stateHint.text
    property alias testHeight: column.implicitHeight
    property alias testReading: reader.running''', 1)
    (tmp_path / 'BarWidget.qml').write_text(code)
    (tmp_path / 'shell.qml').write_text('''import QtQuick
import Quickshell
ShellRoot {
    property int ticks: 0
    property bool initialized: false
    property real stableHeight: 0
    property string stableHint: ""
    property int readingSamples: 0
    BarWidget { id: widget }
    Timer {
        interval: 20; running: true; repeat: true
        onTriggered: {
            ticks++
            if (!initialized && widget.stateLoaded && !widget.testReading) {
                initialized = true
                widget.testInput.text = "unfinished-demo-pin"
                widget.testInput.forceActiveFocus()
                stableHeight = widget.testHeight
                stableHint = widget.testHint
            }
            if (initialized && ticks % 50 === 0) widget.refreshSites()
            if (initialized && widget.testReading) {
                readingSamples++
                if (widget.testHint !== stableHint || widget.testHeight !== stableHeight || widget.testInput.text !== "unfinished-demo-pin") {
                    console.log("POLLING_CHANGED_INPUT_OR_LAYOUT"); Qt.quit(); return
                }
            }
            if (ticks > 170) {
                console.log(initialized && readingSamples > 10 ? "POLLING_STABLE" : "POLLING_NOT_EXERCISED")
                Qt.quit()
            }
        }
    }
}
''')
    result = subprocess.run(['quickshell', '--path', str(tmp_path / 'shell.qml'), '--no-color'],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True,
                            text=True, timeout=10)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and 'POLLING_STABLE' in output, output

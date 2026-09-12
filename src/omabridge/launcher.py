from .i18n import tr

import configparser
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def workspace_executable() -> str | None:
    found = shutil.which("wfica")
    if found:
        return found
    path = Path("/opt/Citrix/ICAClient/wfica")
    return str(path) if path.is_file() and os.access(path, os.X_OK) else None


def prepare_ica(path: Path):
    if not 0 < path.stat().st_size <= 2_000_000:
        raise ValueError(tr("Invalid ICA file size."))
    content = path.read_text(encoding="utf-8-sig")
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read_string(content)
    except configparser.Error as error:
        raise ValueError(tr("The portal did not return a valid ICA file.")) from error
    if "WFClient" not in parser or "ApplicationServers" not in parser:
        raise ValueError(tr("The portal did not return an ICA session."))
    # Workspace removes the launch ticket once consumed. Also clean up on exit.
    for key in list(parser["WFClient"]):
        if key.lower() == "removeicafile":
            del parser["WFClient"][key]
    parser["WFClient"]["RemoveICAFile"] = "yes"
    output = io.StringIO()
    parser.write(output, space_around_delimiters=False)
    path.write_text(output.getvalue(), encoding="utf-8")
    os.chmod(path, 0o600)


def launch_workspace(path: Path):
    executable = workspace_executable()
    if not executable:
        raise ValueError(tr("Citrix Workspace is missing: wfica is not installed. Install Workspace or choose browser mode."))
    prepare_ica(path)
    return subprocess.Popen([executable, str(path)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def download_directory() -> tempfile.TemporaryDirectory:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return tempfile.TemporaryDirectory(prefix="omabridge-", dir=runtime or None)

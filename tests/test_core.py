import json
import os
from pathlib import Path

import pytest

from omabridge.launcher import prepare_ica
from omabridge.models import Credentials, Site, https_url, origin
from omabridge.storage import SecretVault, SiteStore, VaultError
from omabridge.totp import Totp


@pytest.mark.parametrize("timestamp,expected", [(59, "94287082"), (1111111109, "07081804"),
    (1111111111, "14050471"), (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130")])
def test_rfc6238_vectors(timestamp, expected):
    generator = Totp(b"12345678901234567890", digits=8)
    assert generator.code(timestamp) == expected


def test_rfc6238_sha256_sha512():
    assert Totp(b"12345678901234567890123456789012", "sha256", 8).code(59) == "46119246"
    assert Totp(b"1234567890123456789012345678901234567890123456789012345678901234", "sha512", 8).code(59) == "90693936"


def test_provisioning_uri_and_spaces():
    raw = "GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ"
    generator = Totp.parse(raw)
    assert generator.code(59) == "287082"
    assert generator.remaining(59) == 1
    uri = "otpauth://totp/Company:user?secret=" + raw.replace(" ", "") + "&digits=8&algorithm=SHA256&period=60"
    parsed = Totp.parse(uri)
    assert parsed.digits == 8 and parsed.period == 60 and parsed.algorithm == "sha256"


@pytest.mark.parametrize("value", ["123456", "", "not a valid key", "otpauth://hotp/x?secret=GEZDGNBVGY3TQOJQ",
    "otpauth://totp/x?secret=GEZDGNBVGY3TQOJQ&period=0", "otpauth://totp/x?secret=GEZDGNBVGY3TQOJQ&digits=9",
    "otpauth://totp/x?secret=GEZDGNBVGY3TQOJQ&secret=GEZDGNBVGY3TQOJQ"])
def test_invalid_totp(value):
    with pytest.raises(ValueError):
        Totp.parse(value)


@pytest.mark.parametrize("url", ["http://citrix.test", "file:///etc/passwd", "https://user:pass@citrix.test",
    "https://citrix.test:wrong", "https://citrix.test\\@evil.test", "https://citrix.test/\n", "javascript:alert(1)"])
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        https_url(url)


def test_origin_normalization_and_port():
    assert origin("https://CITRIX.test:443/Citrix/StoreWeb/") == "https://citrix.test"
    assert origin("https://citrix.test:8443/") == "https://citrix.test:8443"
    assert origin("https://[::1]:8443/") == "https://[::1]:8443"
    assert origin("https://büro.test") == "https://xn--bro-hoa.test"


def test_sites_roundtrip_private_atomic(tmp_path):
    store = SiteStore(tmp_path / "config")
    sites = [Site("Büro", "https://citrix.test/Citrix/StoreWeb/"), Site("Kunde", "https://other.test", mode="browser")]
    store.save(sites)
    assert store.load() == sites
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert store.directory.stat().st_mode & 0o777 == 0o700
    data = store.path.read_text()
    assert '"password"' not in data and '"totp"' not in data and '"username"' not in data
    assert len(list(store.directory.iterdir())) == 1


def test_save_failure_keeps_previous(tmp_path, monkeypatch):
    store = SiteStore(tmp_path)
    original = [Site("One", "https://one.test")]
    store.save(original)
    def fail(*args):
        raise OSError("Disk full")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        store.save([Site("Two", "https://two.test")])
    assert store.load() == original
    assert len(list(tmp_path.iterdir())) == 1


def test_corrupt_config_never_overwritten(tmp_path):
    store = SiteStore(tmp_path)
    store.path.write_text('{"version": 99, "sites": []}')
    with pytest.raises(ValueError, match="not been overwritten"):
        store.load()
    assert json.loads(store.path.read_text())["version"] == 99


def test_duplicate_ids_rejected(tmp_path):
    site = Site("One", "https://one.test")
    with pytest.raises(ValueError):
        SiteStore(tmp_path).save([site, site])


def test_secrets_repr_redacted():
    assert "secret-password" not in repr(Credentials("user", "secret-password", "secret-seed"))


def test_keyring_unavailable_never_falls_back(monkeypatch, tmp_path):
    import secretstorage
    def fail():
        raise RuntimeError("No D-Bus")
    monkeypatch.setattr(secretstorage, "dbus_init", fail)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(VaultError):
        SecretVault().set("site", Credentials("user", "password", "seed"))
    assert list(tmp_path.iterdir()) == []


def test_ica_validation_and_remove_ticket(tmp_path):
    path = tmp_path / "launch.ica"
    path.write_text("[WFClient]\nRemoveICAFile=no\n[ApplicationServers]\nDesktop=\n[Desktop]\nAddress=server.test\n")
    prepare_ica(path)
    assert "RemoveICAFile=yes" in path.read_text()
    assert "Address=server.test" in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    path.write_text('<html>Sign in</html>')
    with pytest.raises(ValueError):
        prepare_ica(path)


def test_workspace_spawn_argv(tmp_path, monkeypatch):
    import omabridge.launcher as launcher
    path = tmp_path / "ticket with spaces.ica"
    path.write_text("[WFClient]\n[ApplicationServers]\nDesktop=\n")
    monkeypatch.setattr(launcher, "workspace_executable", lambda: "/opt/Citrix/ICAClient/wfica")
    calls = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)))
    launcher.launch_workspace(path)
    assert calls[0][0] == ["/opt/Citrix/ICAClient/wfica", str(path)]
    assert "shell" not in calls[0][1]


def test_site_never_accepts_url_tickets():
    with pytest.raises(ValueError):
        Site("One", "https://one.test/?ticket=secret")

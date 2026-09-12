from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4


def https_url(value: str) -> str:
    if any(ord(c) < 32 for c in value):
        raise ValueError("Die Portal-URL enthält Steuerzeichen.")
    value = value.strip()
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError as error:
        raise ValueError("Die Portal-URL ist ungültig.") from error
    if (url.scheme != "https" or not url.hostname or url.username is not None
            or url.password is not None or any(c.isspace() for c in value)
            or "\\" in value or any(ord(c) < 32 for c in value)):
        raise ValueError("Bitte eine HTTPS-Portal-URL ohne Zugangsdaten eingeben.")
    host = url.hostname.encode("idna").decode("ascii").lower()
    host = f"[{host}]" if ":" in host else host
    netloc = host + (f":{port}" if port and port != 443 else "")
    return urlunsplit(("https", netloc, url.path or "/", url.query, url.fragment))


def origin(value: str) -> str:
    url = urlsplit(https_url(value))
    return f"https://{url.netloc}"


@dataclass
class Site:
    name: str
    url: str
    id: str = field(default_factory=lambda: str(uuid4()))
    mode: str = "workspace"
    auto_login: bool = True
    selectors: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.name = self.name.strip()
        if not self.name or len(self.name) > 80:
            raise ValueError("Der Site-Name muss 1–80 Zeichen lang sein.")
        self.url = https_url(self.url)
        if urlsplit(self.url).query or urlsplit(self.url).fragment:
            raise ValueError("Die Portal-URL ohne Query-Parameter oder Fragment speichern.")
        UUID(self.id)
        if self.mode not in {"workspace", "browser"}:
            raise ValueError("Unbekannter Startmodus.")
        if type(self.auto_login) is not bool:
            raise ValueError("Ungültige Einstellung für die automatische Anmeldung.")
        allowed = {"username", "password", "otp", "submit", "browser", "workspace"}
        if (not isinstance(self.selectors, dict) or set(self.selectors) - allowed
                or any(not isinstance(v, str) or len(v) > 1000 for v in self.selectors.values())):
            raise ValueError("Ungültige Formular-Selektoren.")

    def public_dict(self):
        return asdict(self)


@dataclass(repr=False)
class Credentials:
    username: str = ""
    password: str = ""
    totp: str = ""

    def __repr__(self):
        return "Credentials(<redacted>)"

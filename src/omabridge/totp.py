"""RFC 6238 TOTP, accepting Base32 keys and otpauth provisioning URIs."""
import base64
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit


@dataclass(repr=False, frozen=True)
class Totp:
    secret: bytes
    algorithm: str = "sha1"
    digits: int = 6
    period: int = 30

    @classmethod
    def parse(cls, value: str):
        algorithm, digits, period = "sha1", 6, 30
        value = value.strip()
        if value.startswith("otpauth:"):
            url = urlsplit(value)
            if url.scheme != "otpauth" or url.netloc != "totp":
                raise ValueError("Nur TOTP wird unterstützt, kein HOTP.")
            query = parse_qs(url.query)
            if any(len(v) != 1 for v in query.values()):
                raise ValueError("Mehrdeutige TOTP-Parameter.")
            value = query.get("secret", [""])[0]
            algorithm = query.get("algorithm", ["sha1"])[0].lower()
            try:
                digits = int(query.get("digits", ["6"])[0])
                period = int(query.get("period", ["30"])[0])
            except ValueError as error:
                raise ValueError("Ungültige TOTP-Parameter.") from error
        if algorithm not in {"sha1", "sha256", "sha512"} or digits not in {6, 8} or not 15 <= period <= 120:
            raise ValueError("TOTP benötigt SHA1/256/512, 6/8 Stellen und 15–120 Sekunden.")
        key = "".join(value.upper().split()).rstrip("=")
        try:
            secret = base64.b32decode(key + "=" * ((-len(key)) % 8))
        except (ValueError, base64.binascii.Error) as error:
            raise ValueError("Ungültiger Base32-TOTP-Schlüssel.") from error
        if len(secret) < 10:
            raise ValueError("Einen TOTP-Schlüssel oder otpauth-Link eingeben, keinen Einmalcode.")
        return cls(secret, algorithm, digits, period)

    def code(self, timestamp: float | None = None) -> str:
        timestamp = time.time() if timestamp is None else timestamp
        counter = struct.pack(">Q", int(timestamp) // self.period)
        digest = hmac.new(self.secret, counter, getattr(hashlib, self.algorithm)).digest()
        offset = digest[-1] & 15
        number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff
        return str(number % 10 ** self.digits).zfill(self.digits)

    def remaining(self, timestamp: float | None = None) -> float:
        return self.period - ((time.time() if timestamp is None else timestamp) % self.period)


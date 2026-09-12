"""Optional application access gate; not a replacement for the OS/keyring lock."""
import hashlib
import hmac
import json
import math
import os
import secrets
import tempfile
import time
from pathlib import Path

from .i18n import tr
from .storage import config_directory


class AppLockStore:
    def __init__(self, directory=None, clock=time.time):
        self.path = (directory or config_directory()) / 'app-lock.json'
        self.clock = clock

    def load(self):
        try:
            if self.path.stat().st_size > 4096:
                raise ValueError
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version') != 1 or type(data.get('enabled')) is not bool:
                raise ValueError
            if not data['enabled']:
                return None
            if (data.get('algorithm') != 'scrypt-v1' or data.get('kind') not in {'pin', 'password'}
                    or len(bytes.fromhex(data['salt'])) != 16 or len(bytes.fromhex(data['digest'])) != 32
                    or type(data.get('failures')) is not int or not 0 <= data['failures'] <= 100
                    or type(data.get('retry_after')) not in {int, float}
                    or not 0 <= data['retry_after'] <= 1e12 or not math.isfinite(data['retry_after'])):
                raise ValueError
            return data
        except FileNotFoundError:
            return None
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise ValueError(tr('App lock configuration is invalid. Access remains blocked.')) from error

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix='.app-lock-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump(data, output)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def validate_secret(secret, kind):
        if kind not in {'pin', 'password'} or not secret:
            raise ValueError(tr('Enter a non-empty PIN or password.'))
        if kind == 'pin' and not (secret.isascii() and secret.isdigit()):
            raise ValueError(tr('A PIN must contain only digits (0–9). Any length is allowed.'))

    @staticmethod
    def _derive(secret, salt):
        # OWASP scrypt configuration: 128 MiB memory, fixed cost independent of file input.
        return hashlib.scrypt(secret.encode('utf-8'), salt=salt, n=2**17, r=8, p=1,
                              maxmem=256 * 1024 * 1024, dklen=32)

    def configure(self, secret, kind):
        self.validate_secret(secret, kind)
        salt = secrets.token_bytes(16)
        self._write(dict(version=1, enabled=True, kind=kind, algorithm='scrypt-v1',
                         salt=salt.hex(), digest=self._derive(secret, salt).hex(), failures=0, retry_after=0))

    def disable(self):
        self._write(dict(version=1, enabled=False))

    def verify(self, secret):
        data = self.load()
        # Removing the file during a locked session must not unlock that session.
        if data is None:
            raise ValueError(tr('App lock configuration changed. Restart OmaBridge.'))
        now = self.clock()
        if data['retry_after'] > now:
            raise ValueError(tr('Too many attempts. Try again in {seconds} seconds.',
                                seconds=math.ceil(data['retry_after'] - now)))
        valid = hmac.compare_digest(self._derive(secret, bytes.fromhex(data['salt'])), bytes.fromhex(data['digest']))
        if valid:
            data.update(failures=0, retry_after=0)
        else:
            failures = min(data['failures'] + 1, 100)
            delay = min(2 ** min(failures - 2, 6), 60) if failures >= 3 else 0
            data.update(failures=failures, retry_after=now + delay)
        self._write(data)
        return valid

"""Password hashing and opaque MongoDB-backed sessions."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .errors import DomainError

COOKIE_NAME = 'lab4_session'


def now_utc():
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)
    return f'scrypt${salt}${derived.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        method, salt, expected = encoded.split('$')
        if method != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_digest(token, secret):
    return hmac.new(secret.encode('utf-8'), token.encode('utf-8'), hashlib.sha256).hexdigest()


def new_session(db, settings, user_id):
    token = secrets.token_urlsafe(32)
    now = now_utc()
    db.sessions.insert_one({'_id': token_digest(token, settings.session_secret), 'user_id': user_id,
                            'created_at': now, 'expires_at': now + timedelta(seconds=settings.session_ttl_seconds), 'schema_version': 1})
    return token


def session_user(db, settings, token):
    if not token or len(token) > 128:
        raise DomainError(401, 'authentication', '请先登录')
    session = db.sessions.find_one({'_id': token_digest(token, settings.session_secret), 'expires_at': {'$gt': now_utc()}})
    user = db.users.find_one({'_id': session['user_id']}) if session else None
    if user is None:
        raise DomainError(401, 'authentication', '登录已失效，请重新登录')
    return user


def public_user(user):
    return {'id': user['_id'], 'username': user['username'], 'created_at': user['created_at'].isoformat()}

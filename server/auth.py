import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass


@dataclass
class User:
    id: str
    name: str


def hash_password(password: str, salt: str) -> str:
    """
    >>> a = hash_password("123456", "salt")
    >>> a
    '703453cc3a2dba8d0bed63a5757cc905ee6a6ab357caed7cdf8acdb16d9ea0706647a06259ebc0379bc413b4f0f9dcd51fff8d971f70a99872845a1c908e7462'

    >>> a == hash_password("123456", "salt")
    True

    >>> a == hash_password("123456", "salt2")
    False

    >>> a == hash_password("1234567", "salt")
    False
    """

    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt.encode("utf-8"), n=16 * 1024, r=8, p=1
    ).hex()


class Auth:
    """
    >>> auth = Auth(":memory:")
    >>> auth.register("alice", "alc", "123456")

    >>> auth.login("alc", "hello")
    Traceback (most recent call last):
        ...
    ValueError: Invalid ID or password

    >>> auth.login("bob", "123456")
    Traceback (most recent call last):
        ...
    ValueError: Invalid ID or password

    >>> token = auth.login("alc", "123456")
    >>> len(token)
    43

    >>> auth.get_user(token)
    User(id='alc', name='alice')

    >>> auth.get_user("123456")
    Traceback (most recent call last):
        ...
    ValueError: Invalid token

    >>> token2 = auth.login("alc", "123456", expires_in=0)
    >>> auth.get_user(token2)
    Traceback (most recent call last):
        ...
    ValueError: Invalid token

    >>> auth.logout(token)
    >>> auth.get_user(token)
    Traceback (most recent call last):
        ...
    ValueError: Invalid token
    """

    def __init__(self, path: str) -> None:
        self.db = sqlite3.connect(path)

        with self.db as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    password TEXT NOT NULL,
                    salt TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY NOT NULL,
                    user_id TEXT,
                    expires INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
                """
            )

    def cleanup(self) -> None:
        with self.db as conn:
            conn.execute(
                """
                DELETE FROM sessions WHERE expires < ?
                """,
                (int(time.time()),),
            )

    def register(self, name: str, id: str, password: str) -> None:
        salt = secrets.token_urlsafe()
        password = hash_password(password, salt)

        with self.db as conn:
            conn.execute(
                """
                INSERT INTO users (id, name, password, salt)
                VALUES (?, ?, ?, ?)
                """,
                (id, name, password, salt),
            )

    def login(
        self, user_id: str, password: str, expires_in: int = 365 * 24 * 60 * 60
    ) -> str:
        with self.db as conn:
            cursor = conn.execute(
                """
                SELECT password, salt FROM users WHERE id = ?
                """,
                (user_id,),
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError("Invalid ID or password")

            in_db, salt = row
            param = hash_password(password, salt)

            if in_db != param:
                raise ValueError("Invalid ID or password")

            token = secrets.token_urlsafe(32)
            expires = int(time.time()) + expires_in

            conn.execute(
                """
                INSERT INTO sessions (user_id, token, expires)
                VALUES (?, ?, ?)
                """,
                (user_id, token, expires),
            )

        self.cleanup()

        return token

    def get_user(self, token: str) -> User:
        with self.db as conn:
            cursor = conn.execute(
                """
                SELECT id, name
                FROM sessions, users
                WHERE token = ? AND expires > ? AND sessions.user_id = users.id
                """,
                (token, int(time.time())),
            )
            row = cursor.fetchone()

        if row is None:
            raise ValueError("Invalid token")

        self.cleanup()

        return User(id=row[0], name=row[1])

    def logout(self, token: str) -> None:
        with self.db as conn:
            conn.execute(
                """
                DELETE FROM sessions WHERE token = ?
                """,
                (token,),
            )

        self.cleanup()

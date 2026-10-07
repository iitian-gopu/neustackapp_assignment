import sqlite3
from contextlib import contextmanager
from pathlib import Path

from checkout.config import Settings
from checkout.errors import DomainError

SEED_PRODUCTS = [
    ("coffee", "House Coffee", 1299, 100),
    ("tea", "Green Tea", 749, 100),
    ("mug", "Ceramic Mug", 1599, 25),
    ("filter", "Paper Filters", 399, 100),
    ("grinder", "Hand Grinder", 4999, 2),
]


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings

    def connect(self):
        connection = sqlite3.connect(
            self.settings.database_path,
            timeout=self.settings.busy_timeout_ms / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def initialize(self):
        Path(self.settings.database_path).parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(Path(__file__).with_name("schema.sql").read_text())
        finally:
            connection.close()
        with self.transaction(write=True) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO reward_policy VALUES (1, ?, ?)",
                (self.settings.reward_every, self.settings.discount_percent),
            )
            policy = connection.execute("SELECT * FROM reward_policy").fetchone()
            if (policy["reward_every"], policy["discount_percent"]) != (
                self.settings.reward_every, self.settings.discount_percent
            ):
                raise ValueError("Reward policy differs from the database; use its original values")
            connection.executemany("INSERT OR IGNORE INTO products VALUES (?, ?, ?, ?)", SEED_PRODUCTS)

    @contextmanager
    def transaction(self, *, write=False):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except sqlite3.OperationalError as error:
            connection.rollback()
            if getattr(error, "sqlite_errorcode", 0) & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise DomainError(503, "DATABASE_BUSY", "Retry the request shortly") from error
            raise
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

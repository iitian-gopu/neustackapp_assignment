import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str = "checkout.db"
    reward_every: int = 5
    discount_percent: int = 10
    busy_timeout_ms: int = 5000

    def __post_init__(self):
        if not 1 <= self.reward_every <= 1_000_000:
            raise ValueError("REWARD_EVERY must be between 1 and 1000000")
        if not 1 <= self.discount_percent <= 100:
            raise ValueError("DISCOUNT_PERCENT must be between 1 and 100")
        if self.database_path == ":memory:":
            raise ValueError("Use a file-backed database")
        if self.busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms cannot be negative")

    @classmethod
    def from_env(cls):
        return cls(
            database_path=os.getenv("DATABASE_PATH", "checkout.db"),
            reward_every=int(os.getenv("REWARD_EVERY", "5")),
            discount_percent=int(os.getenv("DISCOUNT_PERCENT", "10")),
        )

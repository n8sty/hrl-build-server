from pathlib import Path

from pydantic import BaseConfig


class Config(BaseConfig):
    db: str = "db.sqlite"
    data_dir: Path = Path("./programs")

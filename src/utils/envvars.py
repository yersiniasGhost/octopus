from typing import Optional
from dotenv import load_dotenv
from pathlib import Path
import os
import sys

from .singleton import Singleton


class EnvVars(metaclass=Singleton):

    def __init__(self):
        # Load .env file - check local directory first, then home directory
        local_env_path = Path.cwd() / ".env"
        home_env_path = Path.home() / ".env"

        if local_env_path.exists():
            print(f"Loading .env from local directory: {local_env_path}")
            load_dotenv(local_env_path, override=True)
        elif home_env_path.exists():
            print(f"Loading .env from home directory: {home_env_path}")
            load_dotenv(home_env_path, override=True)
        else:
            print(f"Warning: .env file not found in {local_env_path} or {home_env_path}. Using defaults and environment variables.")

        self.env_variables = {}
        self.log_path = self.get_env("LOG_PATH", "/var/log/raptor")

        # Application settings
        self.debug = self.get_bool('DEBUG', "False")
        self.log_level = self.get_env('LOG_LEVEL', 'INFO')


    def get_env(self, variable: str, default: Optional[str] = None) -> Optional[str]:
        return self.env_variables.get(variable) or self.env_variables.setdefault(
            variable,
            os.getenv(variable, default)
        )


    def _get_required(self, key: str) -> str:
        value = self.get_env(key)
        if value is None:
            raise ValueError(f"Missing required environment variable: {key}")
        return value

    def get_bool(self, key: str, default: str) -> bool:
        value = self.get_env(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return value.lower() in ('true', '1', 'yes', 'y')


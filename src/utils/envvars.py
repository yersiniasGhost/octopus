from typing import Optional
from dotenv import load_dotenv
from pathlib import Path
import os
import sys

from .singleton import Singleton


class EnvVars(metaclass=Singleton):

    def __init__(self):
        # Load .env files - home directory first (global defaults), then local (overrides)
        local_env_path = Path.cwd() / ".env"
        home_env_path = Path.home() / ".env"

        loaded_any = False

        # First: Load global .env from home directory (base defaults)
        if home_env_path.exists():
            print(f"Loading global .env from home directory: {home_env_path}")
            load_dotenv(home_env_path, override=True)
            loaded_any = True

        # Second: Load local .env (overrides global values)
        if local_env_path.exists():
            print(f"Loading local .env (overrides global): {local_env_path}")
            load_dotenv(local_env_path, override=True)
            loaded_any = True

        if not loaded_any:
            print(f"Warning: .env file not found in {home_env_path} or {local_env_path}. Using defaults and environment variables.")

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


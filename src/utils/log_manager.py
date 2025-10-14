import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .singleton import Singleton
from typing import Dict
from src.utils.envvars import EnvVars


class LogManager(metaclass=Singleton):

    def __init__(self, log_filename: str = "application.log"):
        self._loggers: Dict[str, logging.Logger] = {}
        self._file_handler: logging.Handler | None = None
        self._console_handler: logging.Handler | None = None
        self._log_dir = Path(EnvVars().log_path or "/var/log/raptor")
        self._setup_base_config(log_filename)


    def _setup_base_config(self, log_filename: str):
        """Initialize base logging configuration."""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            print("Warning: Cannot create /var/log/raptor. Ensure proper permissions.")
            # Fallback to current directory
            self._log_dir = Path('.')

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
        )

        # Setup file handler
        if self._file_handler is None:
            try:
                self._file_handler = RotatingFileHandler(
                    self._log_dir / log_filename,
                    maxBytes=10485760,
                    backupCount=5
                )
                self._file_handler.setFormatter(formatter)
            except Exception:
                self._file_handler = None

        # Setup console handler (stdout)
        if self._console_handler is None:
            self._console_handler = logging.StreamHandler()
            self._console_handler.setFormatter(formatter)
        # # Create formatters
        # self.detailed_formatter = logging.Formatter(
        #     '%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
        # )
        # self.simple_formatter = logging.Formatter(
        #     '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        # )



    def get_logger(self, name: str) -> logging.Logger:
        if name not in self._loggers:
            logger = logging.getLogger(name)
            level = EnvVars().log_level
            if isinstance(level, str):
                level = logging._nameToLevel.get(level.upper(), logging.INFO)
            if not isinstance(level, int):
                level = logging.INFO
            logger.setLevel(level)

            # Remove any existing handlers
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)

            # Add file handler if available
            if self._file_handler:
                logger.addHandler(self._file_handler)

            # Always add console handler (stdout)
            if self._console_handler:
                logger.addHandler(self._console_handler)

            # Prevent propagation to root logger
            logger.propagate = False

            self._loggers[name] = logger

        return self._loggers[name]


    def update_all_log_levels(self, level: int):
        """Update log level for all managed loggers."""
        for logger in self._loggers.values():
            logger.setLevel(level)

    def get_all_loggers(self) -> Dict[str, logging.Logger]:
        """Get dictionary of all managed loggers."""
        return self._loggers.copy()


    def configure_library_loggers(self, level=None):
        """Configure third-party libraries to use the same handlers"""
        if level is None:
            level = EnvVars().log_level
        if isinstance(level, str):
            level = logging._nameToLevel.get(level.upper(), logging.INFO)
        if not isinstance(level, int):
            level = logging.INFO

        # Configure FastAPI and related libraries
        for logger_name in [
            "fastapi",
            "uvicorn",
            "uvicorn.access",
            "uvicorn.error",
            "aiomqtt",
        ]:
            lib_logger = logging.getLogger(logger_name)
            lib_logger.setLevel(level)

            # Add file handler if available
            if self._file_handler and not any(isinstance(h, type(self._file_handler)) for h in lib_logger.handlers):
                lib_logger.addHandler(self._file_handler)

            # Always add console handler
            if self._console_handler and not any(isinstance(h, logging.StreamHandler) for h in lib_logger.handlers):
                lib_logger.addHandler(self._console_handler)

            # Prevent propagation to root logger to avoid duplicate logs
            lib_logger.propagate = False

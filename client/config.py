"""
Configuration for Energy Conservation Client Portal

Loads settings from environment variables using the project's EnvVars utility.
"""
import sys
from pathlib import Path

# Add project root to path to access shared utilities
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.envvars import EnvVars

env = EnvVars()


class Config:
    """Flask application configuration."""

    # Flask
    SECRET_KEY = env.get_env('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = env.get_bool('FLASK_DEBUG', 'true')

    # MongoDB - Empower Development (demographic/residential data)
    MONGODB_HOST = env.get_env('MONGODB_HOST', 'localhost')
    MONGODB_PORT = int(env.get_env('MONGODB_PORT', '27017'))
    MONGODB_EMPOWER_DB = env.get_env('MONGODB_DATABASE', 'empower_development')

    # MongoDB - Campaign Data (participant tracking)
    MONGODB_CAMPAIGN_DB = env.get_env('MONGODB_CAMPAIGN', 'campaign_data')

    # Anthropic Claude API
    ANTHROPIC_API_KEY = env.get_env('ANTHROPIC_API_KEY', '')
    CLAUDE_MODEL = 'claude-sonnet-4-20250514'

    # Application settings
    COUNTIES = ['Franklin', 'Cuyahoga']

    @classmethod
    def get_mongo_uri(cls) -> str:
        """Build MongoDB URI from components."""
        return f"mongodb://{cls.MONGODB_HOST}:{cls.MONGODB_PORT}"

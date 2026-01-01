"""
MongoDB connection utilities for the Octopus project

Provides centralized access to MongoDB databases with:
- Singleton client connection
- Named database access via environment variables
- DRY helper functions for common databases

Environment Variables:
    MONGODB_HOST: MongoDB host (default: localhost)
    MONGODB_PORT: MongoDB port (default: 27017)
    MONGODB_DATABASE: Default database name (empower_development)
    MONGODB_CAMPAIGN: Campaign data database (campaign_data)
"""
from typing import Optional
import pymongo.errors
from pymongo import MongoClient
from pymongo.database import Database

from src.utils.singleton import Singleton
from src.utils.envvars import EnvVars
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


class Mongo(metaclass=Singleton):
    """
    MongoDB connection singleton

    Provides centralized access to MongoDB client and multiple databases.
    Reads connection details from environment variables.

    Usage:
        # Get default database
        db = Mongo().database

        # Get named database
        campaign_db = Mongo().get_database('campaign_data')

        # Or use helper functions
        from src.tools.mongo import get_campaign_db
        db = get_campaign_db()
    """

    def __init__(self):
        """Initialize MongoDB connection from environment variables"""
        self._client: Optional[MongoClient] = None
        self._default_db: Optional[Database] = None
        self._db_cache: dict = {}
        self._env = EnvVars()
        self._connect()

    def _connect(self):
        """Establish MongoDB connection"""
        host = self._env.get_env('MONGODB_HOST', 'localhost')
        port = int(self._env.get_env('MONGODB_PORT', '27017'))
        default_database = self._env.get_env('MONGODB_DATABASE', 'empower_development')

        try:
            logger.info(f"Connecting to MongoDB at {host}:{port}")
            self._client = MongoClient(host, port, serverSelectionTimeoutMS=5000)

            # Test connection
            self._client.server_info()
            logger.info("MongoDB connection successful")

            # Set default database
            self._default_db = self._client[default_database]
            self._db_cache[default_database] = self._default_db

        except pymongo.errors.ServerSelectionTimeoutError as e:
            logger.error(f"MongoDB connection timeout: {e}")
            raise
        except pymongo.errors.ConfigurationError as e:
            logger.error(f"Invalid MongoDB configuration: {e}")
            raise
        except Exception as e:
            logger.error(f"MongoDB connection error: {e}")
            raise

    @property
    def client(self) -> MongoClient:
        """Get MongoDB client instance"""
        if self._client is None:
            raise RuntimeError("MongoDB not connected")
        return self._client

    @property
    def database(self) -> Database:
        """Get default MongoDB database (MONGODB_DATABASE)"""
        if self._default_db is None:
            raise RuntimeError("MongoDB not connected")
        return self._default_db

    def get_database(self, db_name: str) -> Database:
        """
        Get a specific database by name.

        Args:
            db_name: Database name to connect to

        Returns:
            MongoDB Database instance
        """
        if self._client is None:
            raise RuntimeError("MongoDB not connected")

        if db_name not in self._db_cache:
            self._db_cache[db_name] = self._client[db_name]
            logger.debug(f"Cached connection to database: {db_name}")

        return self._db_cache[db_name]

    def get_database_from_env(self, env_var: str) -> Database:
        """
        Get database using name from environment variable.

        Args:
            env_var: Environment variable containing database name

        Returns:
            MongoDB Database instance

        Raises:
            ValueError: If environment variable is not set
        """
        db_name = self._env.get_env(env_var)
        if not db_name:
            raise ValueError(f"Environment variable {env_var} is not set")
        return self.get_database(db_name)

    def ensure_indexes(self):
        """Create required indexes for campaigns and participants collections"""
        logger.info("Creating database indexes...")

        # Campaigns indexes
        self.database.campaigns.create_index("campaign_id", unique=True)
        self.database.campaigns.create_index("status")
        self.database.campaigns.create_index("synced_at")

        # Participants indexes
        self.database.participants.create_index(
            [("campaign_id", 1), ("contact_id", 1)], unique=True
        )
        self.database.participants.create_index("campaign_id")
        self.database.participants.create_index("email_address")

        logger.info("Indexes created successfully")


# =============================================================================
# Convenience Functions (DRY helpers for common database access)
# =============================================================================

def get_mongo() -> Mongo:
    """Get the MongoDB singleton instance"""
    return Mongo()


def get_campaign_db() -> Database:
    """
    Get the campaign_data database.

    Uses MONGODB_CAMPAIGN env var, defaults to 'campaign_data'.

    Returns:
        MongoDB Database for campaign data
    """
    mongo = Mongo()
    db_name = mongo._env.get_env('MONGODB_CAMPAIGN', 'campaign_data')
    return mongo.get_database(db_name)


def get_empower_db() -> Database:
    """
    Get the empower_development database.

    Uses MONGODB_DATABASE env var.

    Returns:
        MongoDB Database for empower development data
    """
    return Mongo().database


def get_collection(collection_name: str, database: str = 'campaign_data'):
    """
    Get a specific collection from a database.

    Args:
        collection_name: Name of the collection
        database: Database name (default: campaign_data)

    Returns:
        MongoDB Collection instance
    """
    return Mongo().get_database(database)[collection_name]

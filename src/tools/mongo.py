"""
MongoDB connection singleton for campaign data sync
"""
import logging
import pymongo.errors
from pymongo import MongoClient

from src.utils.singleton import Singleton
from src.utils.envvars import EnvVars

logger = logging.getLogger(__name__)


class Mongo(metaclass=Singleton):
    """
    MongoDB connection singleton

    Provides centralized access to MongoDB client and database.
    Reads connection details from environment variables:
    - MONGODB_HOST (default: localhost)
    - MONGODB_PORT (default: 27017)
    - MONGODB_DATABASE (required)
    """

    def __init__(self):
        """
        Initialize MongoDB connection

        Reads configuration from environment variables
        """
        self._client = None
        self._db = None
        self._connect()

    def _connect(self):
        """Internal method to establish MongoDB connection"""
        # Read connection details from environment
        env = EnvVars()
        host = env.get_env('MONGODB_HOST', 'localhost')
        port = int(env.get_env('MONGODB_PORT', '27017'))
        database = env.get_env('MONGODB_DATABASE')

        if not database:
            raise ValueError("MONGODB_DATABASE environment variable is required")

        try:
            logger.info(f"Connecting to MongoDB at: {host}:{port}")
            self._client = MongoClient(host, port)
            logger.info(f"Using database: {database}")
            self._db = self._client[database]

            # Test connection
            self._client.server_info()
            logger.info("MongoDB connection successful")

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
    def client(self):
        """Get MongoDB client instance"""
        if self._client is None:
            raise RuntimeError("MongoDB not connected.")
        return self._client

    @property
    def database(self):
        """Get MongoDB database instance"""
        if self._db is None:
            raise RuntimeError("MongoDB not connected.")
        return self._db

    def ensure_indexes(self):
        """Create required indexes for campaigns and participants collections"""
        logger.info("Creating database indexes...")

        # Campaigns indexes
        self.database.campaigns.create_index("campaign_id", unique=True)
        self.database.campaigns.create_index("status")
        self.database.campaigns.create_index("synced_at")

        # Participants indexes
        self.database.participants.create_index([("campaign_id", 1), ("contact_id", 1)], unique=True)
        self.database.participants.create_index("campaign_id")
        self.database.participants.create_index("email_address")

        logger.info("Indexes created successfully")

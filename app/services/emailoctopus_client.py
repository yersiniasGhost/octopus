"""
EmailOctopus API Client

Handles all interactions with the EmailOctopus API v1.6.
Documentation: https://emailoctopus.com/api-documentation/v2
"""
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from src.utils.envvars import EnvVars

logger = logging.getLogger(__name__)


class EmailOctopusAPIError(Exception):
    """Base exception for EmailOctopus API errors"""
    pass


class EmailOctopusAuthenticationError(EmailOctopusAPIError):
    """Raised when API authentication fails"""
    pass


class EmailOctopusRateLimitError(EmailOctopusAPIError):
    """Raised when API rate limit is exceeded"""
    pass


class EmailOctopusClient:
    """
    Client for interacting with EmailOctopus API

    Provides methods for retrieving campaign, list, and contact data.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize EmailOctopus API client

        Args:
            api_key: EmailOctopus API key (defaults to environment variable)
            base_url: API base URL (defaults to environment variable or official URL)
        """
        env = EnvVars()

        self.api_key = api_key or env.get_env('EMAILOCTOPUS_API_KEY')
        if not self.api_key:
            raise EmailOctopusAuthenticationError(
                "EmailOctopus API key not found. Set EMAILOCTOPUS_API_KEY in .env"
            )

        self.base_url = base_url or env.get_env(
            'EMAILOCTOPUS_API_BASE_URL',
            'https://emailoctopus.com/api/1.6'
        )

        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })

        logger.info(f"EmailOctopus client initialized with base URL: {self.base_url}")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to EmailOctopus API

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON request body

        Returns:
            JSON response as dictionary

        Raises:
            EmailOctopusAPIError: On API errors
            EmailOctopusAuthenticationError: On authentication failures
            EmailOctopusRateLimitError: On rate limit exceeded
        """
        # Add API key to parameters
        if params is None:
            params = {}
        params['api_key'] = self.api_key

        # Construct full URL
        url = f"{self.base_url}/{endpoint}"

        try:
            logger.debug(f"Making {method} request to {url}")

            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=30
            )

            # Handle HTTP errors
            if response.status_code == 401:
                raise EmailOctopusAuthenticationError(
                    "Invalid API key or unauthorized access"
                )
            elif response.status_code == 429:
                raise EmailOctopusRateLimitError(
                    "API rate limit exceeded. Please try again later."
                )
            elif response.status_code >= 400:
                error_msg = f"API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_msg = f"{error_msg}: {error_data['error'].get('message', 'Unknown error')}"
                except Exception:
                    error_msg = f"{error_msg}: {response.text}"

                logger.error(error_msg)
                raise EmailOctopusAPIError(error_msg)

            # Parse and return JSON response
            return response.json()

        except requests.exceptions.Timeout:
            logger.error(f"Request to {url} timed out")
            raise EmailOctopusAPIError("Request timed out")
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error to {url}")
            raise EmailOctopusAPIError("Connection error")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise EmailOctopusAPIError(f"Request failed: {str(e)}")

    def get_campaigns(
        self,
        limit: int = 100,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Retrieve list of campaigns

        API Documentation: https://emailoctopus.com/api-documentation/v2#tag/Campaign/operation/api_campaigns_get

        Args:
            limit: Number of campaigns to retrieve (default 100, max 100)
            page: Page number for pagination (default 1)

        Returns:
            Dictionary containing:
                - data: List of campaign objects
                - paging: Pagination information

        Example response:
            {
                "data": [
                    {
                        "id": "00000000-0000-0000-0000-000000000000",
                        "status": "SENT",
                        "name": "Campaign name",
                        "subject": "Email subject",
                        "from": {
                            "name": "Sender name",
                            "email_address": "sender@example.com"
                        },
                        "content": {
                            "html": "<html>...",
                            "plain_text": "..."
                        },
                        "created_at": "2024-01-01T12:00:00+00:00",
                        "sent_at": "2024-01-01T13:00:00+00:00"
                    }
                ],
                "paging": {
                    "next": "https://emailoctopus.com/api/1.6/campaigns?api_key=...&page=2",
                    "previous": null
                }
            }
        """
        logger.info(f"Fetching campaigns (limit={limit}, page={page})")

        params = {
            'limit': min(limit, 100),  # API max is 100
            'page': page
        }

        result = self._make_request('GET', 'campaigns', params=params)

        logger.info(f"Retrieved {len(result.get('data', []))} campaigns")
        return result

    def get_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Retrieve single campaign by ID

        Args:
            campaign_id: UUID of the campaign

        Returns:
            Campaign object dictionary
        """
        logger.info(f"Fetching campaign {campaign_id}")

        result = self._make_request('GET', f'campaigns/{campaign_id}')

        logger.info(f"Retrieved campaign: {result.get('name', 'Unknown')}")
        return result

    def get_campaign_report_contacts(
        self,
        campaign_id: str,
        report_type: str,
        limit: int = 100,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Retrieve contacts from a specific campaign report (opened, clicked, bounced, etc.)

        Args:
            campaign_id: UUID of the campaign
            report_type: Type of report (sent, opened, clicked, bounced, complained, unsubscribed)
            limit: Number of contacts to retrieve (default 100, max 100)
            page: Page number for pagination

        Returns:
            Dictionary with data (list of contacts with engagement info) and paging info
        """
        valid_types = ['sent', 'opened', 'clicked', 'bounced', 'complained', 'unsubscribed']
        if report_type not in valid_types:
            raise EmailOctopusAPIError(f"Invalid report type: {report_type}. Must be one of {valid_types}")

        logger.info(f"Fetching {report_type} contacts for campaign {campaign_id}")

        params = {
            'limit': min(limit, 100),
            'page': page
        }

        result = self._make_request('GET', f'campaigns/{campaign_id}/reports/{report_type}', params=params)

        logger.info(f"Retrieved {len(result.get('data', []))} {report_type} contacts")
        return result

    def get_campaign_reports(self, campaign_id: str) -> Dict[str, Any]:
        """
        Retrieve campaign reports/statistics

        Args:
            campaign_id: UUID of the campaign

        Returns:
            Campaign reports including sent, bounced, opened, clicked counts
        """
        logger.info(f"Fetching reports for campaign {campaign_id}")

        result = self._make_request('GET', f'campaigns/{campaign_id}/reports/summary')

        logger.info(f"Retrieved reports for campaign {campaign_id}")
        return result

    def get_lists(self, limit: int = 100, page: int = 1) -> Dict[str, Any]:
        """
        Retrieve list of contact lists

        Args:
            limit: Number of lists to retrieve (default 100, max 100)
            page: Page number for pagination

        Returns:
            Dictionary with data (list of lists) and paging info
        """
        logger.info(f"Fetching lists (limit={limit}, page={page})")

        params = {
            'limit': min(limit, 100),
            'page': page
        }

        result = self._make_request('GET', 'lists', params=params)

        logger.info(f"Retrieved {len(result.get('data', []))} lists")
        return result

    def get_list(self, list_id: str) -> Dict[str, Any]:
        """
        Retrieve single list by ID

        Args:
            list_id: UUID of the list

        Returns:
            List object dictionary
        """
        logger.info(f"Fetching list {list_id}")

        result = self._make_request('GET', f'lists/{list_id}')

        logger.info(f"Retrieved list: {result.get('name', 'Unknown')}")
        return result

    def get_contacts(
        self,
        list_id: str,
        limit: int = 100,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Retrieve contacts from a list

        Args:
            list_id: UUID of the list
            limit: Number of contacts to retrieve (default 100, max 100)
            page: Page number for pagination

        Returns:
            Dictionary with data (list of contacts) and paging info
        """
        logger.info(f"Fetching contacts for list {list_id} (limit={limit}, page={page})")

        params = {
            'limit': min(limit, 100),
            'page': page
        }

        result = self._make_request('GET', f'lists/{list_id}/contacts', params=params)

        logger.info(f"Retrieved {len(result.get('data', []))} contacts")
        return result

    def get_campaign_contacts(
        self,
        campaign_id: str,
        limit: int = 100,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Retrieve contacts from a campaign's associated lists

        Args:
            campaign_id: UUID of the campaign
            limit: Number of contacts to retrieve per list (default 100, max 100)
            page: Page number for pagination

        Returns:
            Dictionary with data (list of contacts) and paging info
        """
        logger.info(f"Fetching contacts for campaign {campaign_id}")

        # First get campaign to find associated lists
        campaign = self.get_campaign(campaign_id)

        # Get list IDs from campaign's 'to' field
        list_ids = campaign.get('to', [])

        if not list_ids:
            logger.warning(f"Campaign {campaign_id} has no associated lists")
            return {'data': [], 'paging': {}}

        # For now, fetch contacts from the first list
        # Future enhancement: combine contacts from multiple lists
        list_id = list_ids[0]
        logger.info(f"Fetching contacts from list {list_id}")

        return self.get_contacts(list_id, limit, page)

    def test_connection(self) -> bool:
        """
        Test API connection and authentication

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to fetch campaigns (simplest API call)
            self.get_campaigns(limit=1)
            logger.info("API connection test successful")
            return True
        except Exception as e:
            logger.error(f"API connection test failed: {str(e)}")
            return False

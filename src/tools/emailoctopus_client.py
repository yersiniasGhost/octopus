"""
EmailOctopus API Client (Standalone version for sync tool)

Handles all interactions with the EmailOctopus API v1.6.
This is a standalone version that doesn't depend on Flask.
"""
import requests
import time
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
                "EmailOctopus API key not found. Set EMAILOCTOPUS_API_KEY environment variable."
            )

        self.base_url = base_url or env.get_env('EMAILOCTOPUS_API_BASE_URL', 'https://emailoctopus.com/api/1.6')
        self.base_url = self.base_url.rstrip('/')

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                     json_data: Optional[Dict] = None, retry_count: int = 0, max_retries: int = 3) -> Dict[str, Any]:
        """
        Make HTTP request to EmailOctopus API

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON request body

        Returns:
            API response as dictionary

        Raises:
            EmailOctopusAPIError: On API errors
        """
        url = f"{self.base_url}/{endpoint}"

        # Add API key to params
        if params is None:
            params = {}
        params['api_key'] = self.api_key

        try:
            logger.debug(f"Making {method} request to {url} with params: {params}")
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=30
            )

            # Check for errors
            if response.status_code == 401:
                raise EmailOctopusAuthenticationError("Invalid API key")
            elif response.status_code == 429:
                # Rate limit with exponential backoff
                if retry_count < max_retries:
                    wait_time = (2 ** retry_count) * 5  # 5, 10, 20 seconds
                    logger.warning(f"Rate limit hit, waiting {wait_time}s before retry {retry_count + 1}/{max_retries}")
                    time.sleep(wait_time)
                    return self._make_request(method, endpoint, params, json_data, retry_count + 1, max_retries)
                else:
                    raise EmailOctopusRateLimitError("API rate limit exceeded after retries")
            elif response.status_code >= 400:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('error', {}).get('message', f"HTTP {response.status_code}")
                raise EmailOctopusAPIError(f"API error: {error_msg}")

            response.raise_for_status()
            result = response.json()
            logger.debug(f"Response status: {response.status_code}, data keys: {list(result.keys()) if isinstance(result, dict) else 'not a dict'}")
            return result

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout for {method} {url}")
            raise EmailOctopusAPIError("Request timeout")
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error for {method} {url}")
            raise EmailOctopusAPIError("Connection error")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {method} {url}: {str(e)}")
            raise EmailOctopusAPIError(f"Request failed: {str(e)}")

    def get_campaigns(self, limit: int = 100, page: int = 1) -> Dict[str, Any]:
        """
        Retrieve list of campaigns

        Args:
            limit: Number of campaigns to return (max 100)
            page: Page number for pagination

        Returns:
            Dictionary with 'data' (list of campaigns) and 'paging' info
        """
        params = {
            'limit': min(limit, 100),
            'page': page
        }
        return self._make_request('GET', 'campaigns', params=params)

    def get_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Retrieve single campaign details

        Args:
            campaign_id: EmailOctopus campaign UUID

        Returns:
            Campaign data dictionary
        """
        return self._make_request('GET', f'campaigns/{campaign_id}')

    def get_campaign_summary(self, campaign_id: str) -> Dict[str, Any]:
        """
        Retrieve campaign summary statistics

        Args:
            campaign_id: EmailOctopus campaign UUID

        Returns:
            Statistics dictionary with sent, opened, clicked, bounced, etc.
        """
        return self._make_request('GET', f'campaigns/{campaign_id}/reports/summary')

    def get_campaign_report_contacts(self, campaign_id: str, report_type: str,
                                    limit: int = 100, page: int = 1, cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve contacts from a specific campaign report (opened, clicked, bounced, etc.)

        Args:
            campaign_id: EmailOctopus campaign UUID
            report_type: Report type (sent, opened, clicked, bounced, complained, unsubscribed)
            limit: Number of contacts to return (max 100)
            page: Page number for pagination (deprecated, use cursor instead)
            cursor: Cursor for pagination (from paging.next 'last' parameter)

        Returns:
            Dictionary with 'data' (list of contacts) and 'paging' info
        """
        valid_types = ['sent', 'opened', 'clicked', 'bounced', 'complained', 'unsubscribed']
        if report_type not in valid_types:
            raise EmailOctopusAPIError(
                f"Invalid report type: {report_type}. Must be one of: {', '.join(valid_types)}"
            )

        params = {
            'limit': min(limit, 100)
        }

        # Use cursor-based pagination if available, otherwise fall back to page number
        if cursor:
            params['last'] = cursor
        else:
            params['page'] = page

        return self._make_request('GET', f'campaigns/{campaign_id}/reports/{report_type}', params=params)

    def get_lists(self, limit: int = 100, page: int = 1) -> Dict[str, Any]:
        """
        Retrieve list of contact lists

        Args:
            limit: Number of lists to return (max 100)
            page: Page number for pagination

        Returns:
            Dictionary with 'data' (list of lists) and 'paging' info
        """
        params = {
            'limit': min(limit, 100),
            'page': page
        }
        return self._make_request('GET', 'lists', params=params)

    def get_list(self, list_id: str) -> Dict[str, Any]:
        """
        Retrieve single list details

        Args:
            list_id: EmailOctopus list UUID

        Returns:
            List data dictionary
        """
        return self._make_request('GET', f'lists/{list_id}')

    def get_contacts(self, list_id: str, limit: int = 100, page: int = 1) -> Dict[str, Any]:
        """
        Retrieve contacts from a list

        Args:
            list_id: EmailOctopus list UUID
            limit: Number of contacts to return (max 100)
            page: Page number for pagination

        Returns:
            Dictionary with 'data' (list of contacts) and 'paging' info
        """
        params = {
            'limit': min(limit, 100),
            'page': page
        }
        return self._make_request('GET', f'lists/{list_id}/contacts', params=params)

    def get_campaign_contacts(self, campaign_id: str, limit: int = 100, page: int = 1) -> Dict[str, Any]:
        """
        Retrieve contacts from a campaign's associated lists

        Args:
            campaign_id: EmailOctopus campaign UUID
            limit: Number of contacts to return (max 100)
            page: Page number for pagination

        Returns:
            Dictionary with 'data' (list of contacts) and 'paging' info
        """
        # Get campaign to find associated lists
        campaign = self.get_campaign(campaign_id)
        list_ids = campaign.get('to', [])

        if not list_ids:
            return {'data': [], 'paging': {}}

        # Get contacts from first list (campaigns typically use one list)
        list_id = list_ids[0]
        return self.get_contacts(list_id, limit, page)

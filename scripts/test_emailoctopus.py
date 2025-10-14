#!/usr/bin/env python3
"""
EmailOctopus API Integration Test Script

Quick verification script to test EmailOctopus API integration.
Run this to verify your API key is configured correctly.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import EmailOctopusClient
from app.services.emailoctopus_client import (
    EmailOctopusAPIError,
    EmailOctopusAuthenticationError,
    EmailOctopusRateLimitError
)


def main():
    """Main test function"""
    print("=" * 60)
    print("EmailOctopus API Integration Test")
    print("=" * 60)
    print()

    # Test 1: Client initialization
    print("Test 1: Initializing EmailOctopus client...")
    try:
        client = EmailOctopusClient()
        print("✓ Client initialized successfully")
        print()
    except EmailOctopusAuthenticationError as e:
        print(f"✗ Authentication error: {e}")
        print("\nPlease check your EMAILOCTOPUS_API_KEY in .env file")
        return 1
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1

    # Test 2: Connection test
    print("Test 2: Testing API connection...")
    try:
        is_connected = client.test_connection()
        if is_connected:
            print("✓ Successfully connected to EmailOctopus API")
            print()
        else:
            print("✗ Connection test failed")
            return 1
    except EmailOctopusAuthenticationError:
        print("✗ Authentication failed - Invalid API key")
        print("\nGet your API key from: https://emailoctopus.com/api-documentation")
        return 1
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return 1

    # Test 3: Retrieve campaigns
    print("Test 3: Retrieving campaigns...")
    try:
        result = client.get_campaigns(limit=5, page=1)
        campaigns = result.get('data', [])
        paging = result.get('paging', {})

        print(f"✓ Found {len(campaigns)} campaign(s)")

        if campaigns:
            print("\nCampaigns:")
            for i, campaign in enumerate(campaigns, 1):
                print(f"\n{i}. {campaign.get('name', 'Unnamed')}")
                print(f"   Status: {campaign.get('status', 'Unknown')}")
                print(f"   Subject: {campaign.get('subject', 'N/A')}")
                if campaign.get('from'):
                    print(f"   From: {campaign['from'].get('name', 'Unknown')}")
                if campaign.get('created_at'):
                    print(f"   Created: {campaign['created_at'][:10]}")
        else:
            print("\nNo campaigns found in your EmailOctopus account.")
            print("Create a campaign in EmailOctopus to test further.")

        print()

    except EmailOctopusAPIError as e:
        print(f"✗ API error: {e}")
        return 1
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1

    # Test 4: Get campaign details (if campaigns exist)
    if campaigns and len(campaigns) > 0:
        print("Test 4: Retrieving campaign details...")
        try:
            campaign_id = campaigns[0]['id']
            campaign = client.get_campaign(campaign_id)
            print(f"✓ Retrieved details for: {campaign.get('name', 'Unnamed')}")

            # Try to get reports
            try:
                reports = client.get_campaign_reports(campaign_id)
                print(f"✓ Retrieved campaign reports")
                print(f"   Sent: {reports.get('sent', 0)}")
                print(f"   Opened: {reports.get('opened', 0)}")
                print(f"   Clicked: {reports.get('clicked', 0)}")
            except EmailOctopusAPIError:
                print("   (Reports not available for this campaign)")

            print()

        except EmailOctopusAPIError as e:
            print(f"✗ Error retrieving campaign details: {e}")
            return 1

    # Test 5: Get lists
    print("Test 5: Retrieving lists...")
    try:
        lists = client.get_lists(limit=5, page=1)
        list_data = lists.get('data', [])
        print(f"✓ Found {len(list_data)} list(s)")

        if list_data:
            print("\nLists:")
            for i, lst in enumerate(list_data, 1):
                print(f"   {i}. {lst.get('name', 'Unnamed')}")

        print()

    except EmailOctopusAPIError as e:
        print(f"✗ API error: {e}")
        return 1

    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print("✓ All tests passed!")
    print()
    print("Next steps:")
    print("1. Start the application: octopus run")
    print("2. Login at: http://localhost:5000/login")
    print("3. View campaigns at: http://localhost:5000/campaigns")
    print()
    print("API Integration Status: ✓ Ready")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

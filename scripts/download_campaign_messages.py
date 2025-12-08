#!/usr/bin/env python3
"""
Download campaign messages from EmailOctopus API.

Saves campaign content (HTML and plain text) to data/exports/campaign_messages/
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools.emailoctopus_client import EmailOctopusClient


def sanitize_filename(name: str) -> str:
    """Create safe filename from campaign name."""
    # Remove/replace problematic characters
    safe = name.replace('/', '_').replace('\\', '_').replace(':', '_')
    safe = safe.replace('"', '').replace("'", '').replace('?', '').replace('*', '')
    safe = safe.replace('<', '').replace('>', '').replace('|', '')
    # Truncate if too long
    return safe[:100] if len(safe) > 100 else safe


def download_all_campaigns():
    """Download all campaigns from EmailOctopus."""
    client = EmailOctopusClient()
    output_dir = project_root / 'data' / 'exports' / 'campaign_messages'
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching campaigns from EmailOctopus...")

    all_campaigns = []
    page = 1

    while True:
        response = client.get_campaigns(limit=100, page=page)
        campaigns = response.get('data', [])

        if not campaigns:
            break

        all_campaigns.extend(campaigns)
        print(f"  Page {page}: fetched {len(campaigns)} campaigns (total: {len(all_campaigns)})")

        # Check for more pages
        paging = response.get('paging', {})
        if not paging.get('next'):
            break
        page += 1

    print(f"\nTotal campaigns found: {len(all_campaigns)}")
    print(f"\nDownloading campaign content...")

    # Create index file
    index = []

    for i, campaign in enumerate(all_campaigns, 1):
        campaign_id = campaign['id']
        name = campaign.get('name', 'Unknown')
        subject = campaign.get('subject', '')
        status = campaign.get('status', '')
        sent_at = campaign.get('sent_at', '')

        # Get full campaign details (includes content)
        full_campaign = client.get_campaign(campaign_id)
        content = full_campaign.get('content', {})
        html_content = content.get('html', '')
        plain_text = content.get('plain_text', '')

        # Create safe filename
        safe_name = sanitize_filename(name)
        filename = f"{campaign_id}_{safe_name}"

        # Save HTML
        html_path = output_dir / f"{filename}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # Save plain text
        txt_path = output_dir / f"{filename}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(plain_text)

        # Save metadata JSON
        meta = {
            'campaign_id': campaign_id,
            'name': name,
            'subject': subject,
            'status': status,
            'sent_at': sent_at,
            'created_at': campaign.get('created_at', ''),
            'from': campaign.get('from', {}),
            'to_lists': campaign.get('to', []),
            'html_file': f"{filename}.html",
            'txt_file': f"{filename}.txt"
        }

        meta_path = output_dir / f"{filename}.json"
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2)

        # Add to index
        index.append({
            'campaign_id': campaign_id,
            'name': name,
            'subject': subject,
            'status': status,
            'sent_at': sent_at,
            'filename_base': filename
        })

        print(f"  [{i}/{len(all_campaigns)}] {name}")

    # Save index file
    index_path = output_dir / '_index.json'
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump({
            'downloaded_at': datetime.now().isoformat(),
            'total_campaigns': len(index),
            'campaigns': index
        }, f, indent=2)

    print(f"\n✅ Downloaded {len(all_campaigns)} campaigns to {output_dir}")
    print(f"   Index file: {index_path}")


if __name__ == '__main__':
    download_all_campaigns()

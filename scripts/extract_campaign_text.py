#!/usr/bin/env python3
"""
Extract text content from campaign HTML files.

Reads HTML files from data/exports/campaign_messages/ and extracts
readable text content for classification.
"""
import json
import sys
from pathlib import Path
from bs4 import BeautifulSoup

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def extract_text_from_html(html_content: str) -> str:
    """Extract readable text from HTML content."""
    soup = BeautifulSoup(html_content, 'lxml')

    # Remove script and style elements
    for element in soup(['script', 'style', 'head', 'title', 'meta', '[document]']):
        element.decompose()

    # Get text
    text = soup.get_text(separator=' ', strip=True)

    # Clean up whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = ' '.join(lines)

    # Remove excessive spaces
    while '  ' in text:
        text = text.replace('  ', ' ')

    return text


def main():
    """Extract text from all campaign HTML files."""
    base_dir = project_root / 'data' / 'exports' / 'campaign_messages'
    output_file = base_dir / '_campaign_texts.json'

    # Load index
    index_file = base_dir / '_index.json'
    with open(index_file, 'r') as f:
        index = json.load(f)

    campaigns = index['campaigns']
    results = []

    print(f"Extracting text from {len(campaigns)} campaigns...\n")

    for i, campaign in enumerate(campaigns, 1):
        campaign_id = campaign['campaign_id']
        name = campaign['name']
        subject = campaign['subject']
        filename_base = campaign['filename_base']

        # Read HTML file
        html_file = base_dir / f"{filename_base}.html"

        if html_file.exists():
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()

            text = extract_text_from_html(html_content)

            # Truncate for display (first 500 chars)
            text_preview = text[:500] + "..." if len(text) > 500 else text

            results.append({
                'campaign_id': campaign_id,
                'name': name,
                'subject': subject,
                'text_content': text,
                'text_preview': text_preview
            })

            print(f"[{i}/{len(campaigns)}] {name}")
            print(f"    Subject: {subject}")
            print(f"    Text: {text_preview[:200]}...")
            print()
        else:
            print(f"[{i}/{len(campaigns)}] {name} - HTML file not found!")
            results.append({
                'campaign_id': campaign_id,
                'name': name,
                'subject': subject,
                'text_content': '',
                'text_preview': ''
            })

    # Save results
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_campaigns': len(results),
            'campaigns': results
        }, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Extracted text from {len(results)} campaigns")
    print(f"   Output file: {output_file}")


if __name__ == '__main__':
    main()

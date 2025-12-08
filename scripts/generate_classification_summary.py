#!/usr/bin/env python3
"""
Generate a classification summary for campaign messages.

Groups campaigns by unique content templates and prepares for LLM classification.
"""
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def normalize_subject(subject: str) -> str:
    """Normalize subject line for grouping (remove org-specific variations)."""
    # Remove template variables and normalize
    normalized = subject
    normalized = re.sub(r'\{\{[^}]+\}\}', '{{VAR}}', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def extract_message_template(name: str) -> str:
    """Extract message template name from campaign name."""
    # Remove org prefix (OHCAC_, IMPACT_, MVCAP_, COAD_, OHCA_)
    clean = re.sub(r'^(OHCAC?|IMPACT|MVCAP|COAD)_', '', name)
    # Remove date suffix
    clean = re.sub(r'_\d{8}.*$', '', clean)
    # Remove (copy) suffix
    clean = re.sub(r'\s*\(copy\)$', '', clean)
    return clean.strip()


def main():
    """Generate classification summary."""
    base_dir = project_root / 'data' / 'exports' / 'campaign_messages'

    # Load extracted texts
    texts_file = base_dir / '_campaign_texts.json'
    with open(texts_file, 'r') as f:
        data = json.load(f)

    campaigns = data['campaigns']

    # Group by subject line (normalized)
    by_subject = defaultdict(list)
    for c in campaigns:
        norm_subj = normalize_subject(c['subject'])
        by_subject[norm_subj].append(c)

    # Group by message template
    by_template = defaultdict(list)
    for c in campaigns:
        template = extract_message_template(c['name'])
        by_template[template].append(c)

    print("=" * 80)
    print("CAMPAIGN CLASSIFICATION SUMMARY")
    print("=" * 80)
    print(f"\nTotal campaigns: {len(campaigns)}")
    print(f"Unique subject lines: {len(by_subject)}")
    print(f"Unique message templates: {len(by_template)}")

    print("\n" + "=" * 80)
    print("UNIQUE MESSAGE TEMPLATES (for classification)")
    print("=" * 80)

    # For each unique template, show representative sample
    templates_for_classification = []

    for template_name, template_campaigns in sorted(by_template.items()):
        # Get first campaign as representative sample
        sample = template_campaigns[0]

        # Get organizations that received this template
        orgs = set()
        for c in template_campaigns:
            org_match = re.match(r'^(OHCAC?|IMPACT|MVCAP|COAD)_', c['name'])
            if org_match:
                orgs.add(org_match.group(1))

        # Get full text (first 800 chars for classification)
        full_text = sample.get('text_content', '')
        # Clean up preview text and spacer characters
        full_text = re.sub(r'\{\{PreviewText\}\}.*?\{% endif %\}', '', full_text)
        full_text = re.sub(r'[‌\u200c]+', '', full_text)  # Remove zero-width chars
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        templates_for_classification.append({
            'template_name': template_name,
            'campaign_count': len(template_campaigns),
            'organizations': list(orgs),
            'subject': sample['subject'],
            'text_preview': full_text[:1000],
            'campaign_ids': [c['campaign_id'] for c in template_campaigns]
        })

        print(f"\n{'─' * 80}")
        print(f"TEMPLATE: {template_name}")
        print(f"Campaigns: {len(template_campaigns)} | Orgs: {', '.join(sorted(orgs))}")
        print(f"Subject: {sample['subject']}")
        print(f"Text: {full_text[:600]}...")
        print()

    # Save templates for classification
    output_file = base_dir / '_templates_for_classification.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_campaigns': len(campaigns),
            'unique_templates': len(templates_for_classification),
            'templates': templates_for_classification
        }, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"Saved {len(templates_for_classification)} templates to: {output_file}")
    print("=" * 80)


if __name__ == '__main__':
    main()

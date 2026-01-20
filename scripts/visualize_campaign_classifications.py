#!/usr/bin/env python3
"""
Visualize campaigns grouped by their message classification types.

Creates a graphic showing how each campaign belongs to different classification categories.
Database: campaign_data, Collection: campaigns
"""
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pymongo import MongoClient
from src.utils.envvars import EnvVars


# Classification type colors and labels
CLASSIFICATION_COLORS = {
    'urgency_deadline': '#FF6B6B',      # Red
    'savings_financial': '#4ECDC4',      # Teal
    'relief_reassurance': '#45B7D1',     # Blue
    'informational': '#96CEB4',          # Green
    'personalized_qualified': '#FFEAA7', # Yellow
    'motivational_struggle': '#DDA0DD',  # Plum
}

CLASSIFICATION_LABELS = {
    'urgency_deadline': 'Urgency & Deadline',
    'savings_financial': 'Savings & Financial',
    'relief_reassurance': 'Relief & Reassurance',
    'informational': 'Informational',
    'personalized_qualified': 'Personalized & Qualified',
    'motivational_struggle': 'Motivational / Struggle',
}


def fetch_campaigns():
    """Fetch all campaigns with their message_types from MongoDB."""
    env = EnvVars()
    client = MongoClient(env.get_env('MONGODB_URI'))
    db = client['campaign_data']
    campaigns_collection = db.campaigns

    # Get campaigns with message_types
    campaigns = list(campaigns_collection.find(
        {'message_types': {'$exists': True, '$ne': None, '$not': {'$size': 0}}},
        {'campaign_id': 1, 'name': 1, 'message_types': 1, 'campaign_type': 1,
         'subject': 1, 'sent_at': 1, 'status': 1}
    ))

    print(f"Found {len(campaigns)} campaigns with message_types")
    return campaigns


def create_classification_matrix_view(campaigns):
    """Create a matrix-style visualization showing campaign-to-classification mapping."""
    # Build classification -> campaigns mapping
    classification_to_campaigns = defaultdict(list)

    for campaign in campaigns:
        for msg_type in campaign.get('message_types', []):
            name = campaign.get('name', campaign.get('campaign_id', 'Unknown'))[:40]
            classification_to_campaigns[msg_type].append(name)

    # Sort by number of campaigns
    sorted_classifications = sorted(
        classification_to_campaigns.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )

    # Create figure
    fig, ax = plt.subplots(figsize=(16, 10))

    # Calculate layout
    y_positions = {}
    current_y = 0
    y_spacing = 1.2

    for classification, campaign_names in sorted_classifications:
        y_positions[classification] = current_y
        current_y += max(1, len(campaign_names) * 0.15) + y_spacing

    # Draw classification boxes and campaigns
    for classification, campaign_names in sorted_classifications:
        y = y_positions[classification]
        color = CLASSIFICATION_COLORS.get(classification, '#888888')
        label = CLASSIFICATION_LABELS.get(classification, classification)

        # Classification label box
        rect = mpatches.FancyBboxPatch(
            (0, y - 0.4), 3, 0.8,
            boxstyle="round,pad=0.05",
            facecolor=color, edgecolor='black', linewidth=2,
            alpha=0.9
        )
        ax.add_patch(rect)
        ax.text(1.5, y, f"{label}\n({len(campaign_names)} campaigns)",
                ha='center', va='center', fontsize=10, fontweight='bold')

        # Campaign names (truncated)
        x_start = 4
        campaign_display = campaign_names[:12]  # Show max 12 per classification

        for i, name in enumerate(campaign_display):
            col = i % 4
            row = i // 4
            x = x_start + col * 4
            y_offset = y - row * 0.35 + 0.2

            # Small campaign box
            camp_rect = mpatches.FancyBboxPatch(
                (x, y_offset - 0.12), 3.8, 0.25,
                boxstyle="round,pad=0.02",
                facecolor='white', edgecolor=color, linewidth=1.5,
                alpha=0.8
            )
            ax.add_patch(camp_rect)

            # Truncate name
            display_name = name[:25] + '...' if len(name) > 25 else name
            ax.text(x + 1.9, y_offset, display_name,
                    ha='center', va='center', fontsize=7)

        if len(campaign_names) > 12:
            ax.text(x_start + 14, y, f"+{len(campaign_names) - 12} more",
                    ha='left', va='center', fontsize=8, style='italic', color='gray')

    # Set axis limits and labels
    ax.set_xlim(-0.5, 20)
    ax.set_ylim(-1, current_y + 1)
    ax.axis('off')

    plt.title('Campaign Message Classification Mapping\n(campaign_data.campaigns collection)',
              fontsize=14, fontweight='bold', pad=20)

    return fig


def create_sankey_style_view(campaigns):
    """Create a Sankey-style flow visualization."""
    # Build relationships
    classification_to_campaigns = defaultdict(set)
    campaign_to_classifications = defaultdict(list)

    for campaign in campaigns:
        name = campaign.get('name', campaign.get('campaign_id', 'Unknown'))
        for msg_type in campaign.get('message_types', []):
            classification_to_campaigns[msg_type].add(name)
            campaign_to_classifications[name].append(msg_type)

    fig, ax = plt.subplots(figsize=(18, 12))

    # Left side: Classifications
    classifications = list(CLASSIFICATION_COLORS.keys())
    n_classifications = len(classifications)
    class_y_positions = np.linspace(0.9, 0.1, n_classifications)

    # Calculate campaign positions (right side)
    # Group campaigns by their primary classification (first in list)
    campaign_groups = defaultdict(list)
    for campaign in campaigns:
        name = campaign.get('name', campaign.get('campaign_id', 'Unknown'))
        types = campaign.get('message_types', [])
        if types:
            primary = types[0]
            campaign_groups[primary].append((name, types))

    # Draw classification boxes (left)
    class_x = 0.08
    class_width = 0.15

    for i, classification in enumerate(classifications):
        y = class_y_positions[i]
        color = CLASSIFICATION_COLORS[classification]
        label = CLASSIFICATION_LABELS[classification]
        count = len(classification_to_campaigns[classification])

        rect = mpatches.FancyBboxPatch(
            (class_x - class_width/2, y - 0.025), class_width, 0.05,
            boxstyle="round,pad=0.01",
            facecolor=color, edgecolor='black', linewidth=2,
            transform=ax.transAxes
        )
        ax.add_patch(rect)
        ax.text(class_x, y, f"{label}\n({count})",
                transform=ax.transAxes, ha='center', va='center',
                fontsize=8, fontweight='bold')

    # Draw campaigns (right side) grouped by primary classification
    camp_x = 0.75

    all_campaigns = []
    for classification in classifications:
        camps = campaign_groups.get(classification, [])
        for name, types in camps:
            all_campaigns.append((name, types, classification))

    if all_campaigns:
        n_camps = min(len(all_campaigns), 50)  # Limit display
        camp_y_positions = np.linspace(0.95, 0.05, n_camps)

        for i, (name, types, primary) in enumerate(all_campaigns[:n_camps]):
            y = camp_y_positions[i]
            primary_color = CLASSIFICATION_COLORS.get(primary, '#888888')

            # Campaign box
            rect = mpatches.FancyBboxPatch(
                (camp_x - 0.12, y - 0.012), 0.24, 0.022,
                boxstyle="round,pad=0.005",
                facecolor='white', edgecolor=primary_color, linewidth=1.5,
                transform=ax.transAxes
            )
            ax.add_patch(rect)

            # Campaign name (truncated)
            display_name = name[:30] + '...' if len(name) > 30 else name
            ax.text(camp_x, y, display_name, transform=ax.transAxes,
                    ha='center', va='center', fontsize=6)

            # Draw connection lines to all classifications
            for msg_type in types:
                if msg_type in classifications:
                    class_idx = classifications.index(msg_type)
                    class_y = class_y_positions[class_idx]
                    color = CLASSIFICATION_COLORS[msg_type]

                    # Draw curved connection
                    ax.annotate('', xy=(camp_x - 0.12, y),
                               xytext=(class_x + class_width/2, class_y),
                               arrowprops=dict(arrowstyle='-', color=color,
                                             alpha=0.3, connectionstyle='arc3,rad=0.1'),
                               transform=ax.transAxes)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    plt.title('Campaign ↔ Classification Relationships\n(Lines show which classifications each campaign has)',
              fontsize=14, fontweight='bold')

    # Add subtitle with stats
    total_campaigns = len(campaigns)
    total_relationships = sum(len(c.get('message_types', [])) for c in campaigns)
    ax.text(0.5, 0.02, f"Total: {total_campaigns} campaigns with {total_relationships} classification tags",
            transform=ax.transAxes, ha='center', fontsize=10, style='italic')

    return fig


def create_summary_bar_chart(campaigns):
    """Create a summary bar chart of classification distribution."""
    # Count campaigns per classification
    classification_counts = defaultdict(int)
    for campaign in campaigns:
        for msg_type in campaign.get('message_types', []):
            classification_counts[msg_type] += 1

    fig, ax = plt.subplots(figsize=(12, 6))

    classifications = list(CLASSIFICATION_COLORS.keys())
    counts = [classification_counts.get(c, 0) for c in classifications]
    colors = [CLASSIFICATION_COLORS[c] for c in classifications]
    labels = [CLASSIFICATION_LABELS[c] for c in classifications]

    bars = ax.barh(labels, counts, color=colors, edgecolor='black', linewidth=1.5)

    # Add count labels
    for bar, count in zip(bars, counts):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                str(count), va='center', fontsize=10, fontweight='bold')

    ax.set_xlabel('Number of Campaigns', fontsize=12)
    ax.set_title('Campaigns by Message Classification Type\n(campaign_data.campaigns collection)',
                 fontsize=14, fontweight='bold')
    ax.set_xlim(0, max(counts) * 1.15)

    plt.tight_layout()
    return fig


def create_multi_tag_visualization(campaigns):
    """Show campaigns with multiple classification tags."""
    # Find campaigns with multiple tags
    multi_tag_campaigns = [c for c in campaigns if len(c.get('message_types', [])) > 1]

    fig, ax = plt.subplots(figsize=(16, 10))

    if not multi_tag_campaigns:
        ax.text(0.5, 0.5, 'No campaigns with multiple classifications found',
                ha='center', va='center', fontsize=14)
        return fig

    # Sort by number of tags
    multi_tag_campaigns.sort(key=lambda x: len(x.get('message_types', [])), reverse=True)

    # Create grid layout
    n_campaigns = min(len(multi_tag_campaigns), 30)
    y_positions = np.linspace(0.95, 0.05, n_campaigns)

    for i, campaign in enumerate(multi_tag_campaigns[:n_campaigns]):
        y = y_positions[i]
        name = campaign.get('name', campaign.get('campaign_id', 'Unknown'))[:35]
        types = campaign.get('message_types', [])

        # Campaign name
        ax.text(0.02, y, name, transform=ax.transAxes, ha='left', va='center',
                fontsize=8, fontweight='bold')

        # Classification tags
        x_tag = 0.35
        for msg_type in types:
            color = CLASSIFICATION_COLORS.get(msg_type, '#888888')
            label = CLASSIFICATION_LABELS.get(msg_type, msg_type)[:15]

            rect = mpatches.FancyBboxPatch(
                (x_tag, y - 0.012), 0.12, 0.022,
                boxstyle="round,pad=0.003",
                facecolor=color, edgecolor='black', linewidth=1,
                alpha=0.8, transform=ax.transAxes
            )
            ax.add_patch(rect)
            ax.text(x_tag + 0.06, y, label, transform=ax.transAxes,
                    ha='center', va='center', fontsize=6)
            x_tag += 0.13

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    plt.title(f'Campaigns with Multiple Classification Tags ({len(multi_tag_campaigns)} total)\n'
              'Each campaign can belong to multiple message categories',
              fontsize=14, fontweight='bold')

    return fig


def main():
    """Generate all visualizations."""
    print("=" * 60)
    print("Campaign Classification Visualization")
    print(f"Database: campaign_data | Collection: campaigns")
    print("=" * 60)

    # Fetch data
    campaigns = fetch_campaigns()

    if not campaigns:
        print("No campaigns found with message_types!")
        return

    # Output directory
    output_dir = project_root / 'data' / 'exports' / 'visualizations'
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M')

    # Generate visualizations
    print("\nGenerating visualizations...")

    # 1. Summary bar chart
    print("  - Summary bar chart...")
    fig1 = create_summary_bar_chart(campaigns)
    fig1.savefig(output_dir / f'{timestamp}_campaign_classification_summary.png',
                 dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig1)

    # 2. Matrix view
    print("  - Classification matrix view...")
    fig2 = create_classification_matrix_view(campaigns)
    fig2.savefig(output_dir / f'{timestamp}_campaign_classification_matrix.png',
                 dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig2)

    # 3. Sankey-style flow
    print("  - Sankey-style flow diagram...")
    fig3 = create_sankey_style_view(campaigns)
    fig3.savefig(output_dir / f'{timestamp}_campaign_classification_flow.png',
                 dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig3)

    # 4. Multi-tag visualization
    print("  - Multi-tag campaign view...")
    fig4 = create_multi_tag_visualization(campaigns)
    fig4.savefig(output_dir / f'{timestamp}_campaign_multi_tags.png',
                 dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig4)

    print(f"\nVisualization saved to: {output_dir}")
    print(f"Files created:")
    print(f"  - {timestamp}_campaign_classification_summary.png")
    print(f"  - {timestamp}_campaign_classification_matrix.png")
    print(f"  - {timestamp}_campaign_classification_flow.png")
    print(f"  - {timestamp}_campaign_multi_tags.png")

    # Print summary statistics
    print("\n" + "=" * 60)
    print("Summary Statistics:")
    print("=" * 60)

    classification_counts = defaultdict(int)
    for campaign in campaigns:
        for msg_type in campaign.get('message_types', []):
            classification_counts[msg_type] += 1

    for msg_type, count in sorted(classification_counts.items(), key=lambda x: -x[1]):
        label = CLASSIFICATION_LABELS.get(msg_type, msg_type)
        print(f"  {label}: {count} campaigns")

    multi_tag = sum(1 for c in campaigns if len(c.get('message_types', [])) > 1)
    print(f"\n  Campaigns with multiple tags: {multi_tag}")
    print(f"  Total campaigns visualized: {len(campaigns)}")


if __name__ == '__main__':
    main()

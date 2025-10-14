#!/usr/bin/env python3
"""
EmailOctopus Campaign Data Sync Tool

Standalone CLI tool to download all campaign data from EmailOctopus,
store in MongoDB, and export to CSV files.

Usage:
    python scripts/sync_campaigns.py --all                    # Sync all campaigns
    python scripts/sync_campaigns.py --campaign <id>          # Sync specific campaign
    python scripts/sync_campaigns.py --incremental --hours 24 # Sync campaigns older than 24h
    python scripts/sync_campaigns.py --export-csv             # Export MongoDB data to CSV
    python scripts/sync_campaigns.py --stats                  # Show sync statistics
"""
import argparse
import logging
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.sync.campaign_sync import CampaignSync
from src.utils.envvars import EnvVars


def setup_logging(verbose: bool = False):
    """Configure logging"""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Reduce noise from some libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('pymongo').setLevel(logging.WARNING)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='EmailOctopus Campaign Data Sync Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Sync all campaigns:
    python scripts/sync_campaigns.py --all

  Sync specific campaign:
    python scripts/sync_campaigns.py --campaign abc-123-def

  Incremental sync (campaigns older than 24 hours):
    python scripts/sync_campaigns.py --incremental --hours 24

  Export MongoDB data to CSV:
    python scripts/sync_campaigns.py --export-csv

  Show sync statistics:
    python scripts/sync_campaigns.py --stats
        """
    )

    # Operation modes
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--all', action='store_true',
                           help='Sync all campaigns')
    mode_group.add_argument('--campaign', type=str, metavar='ID',
                           help='Sync specific campaign by ID')
    mode_group.add_argument('--incremental', action='store_true',
                           help='Incremental sync (only campaigns needing update)')
    mode_group.add_argument('--export-csv', action='store_true',
                           help='Export all MongoDB campaigns to CSV')
    mode_group.add_argument('--stats', action='store_true',
                           help='Show sync statistics')

    # Options
    parser.add_argument('--hours', type=int, default=24,
                       help='Hours threshold for incremental sync (default: 24)')
    parser.add_argument('--export-dir', type=str, default='data/exports',
                       help='Directory for CSV exports (default: data/exports)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose logging output')

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # Check required environment variables
        env = EnvVars()
        if not env.get_env('MONGODB_DATABASE'):
            logger.error("MongoDB database not configured!")
            logger.error("Set MONGODB_DATABASE environment variable in .env")
            logger.error("Optional: MONGODB_HOST (default: localhost), MONGODB_PORT (default: 27017)")
            sys.exit(1)

        # Initialize sync orchestrator
        logger.info("Initializing campaign sync...")
        sync = CampaignSync(export_dir=args.export_dir)

        # Execute requested operation
        if args.all:
            logger.info("Mode: Sync all campaigns")
            stats = sync.sync_all_campaigns()
            print_stats(stats)

        elif args.campaign:
            logger.info(f"Mode: Sync specific campaign {args.campaign}")
            stats = sync.sync_all_campaigns(campaign_ids=[args.campaign])
            print_stats(stats)

        elif args.incremental:
            logger.info(f"Mode: Incremental sync (campaigns older than {args.hours}h)")
            stats = sync.sync_incremental(hours=args.hours)
            print_stats(stats)

        elif args.export_csv:
            logger.info("Mode: Export MongoDB to CSV")
            count = sync.export_all_to_csv()
            logger.info(f"✓ Exported {count} campaigns to CSV")

        elif args.stats:
            logger.info("Mode: Show statistics")
            show_database_stats(sync)

        logger.info("✓ Operation completed successfully")
        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\n⚠ Operation cancelled by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"✗ Fatal error: {e}", exc_info=True)
        sys.exit(1)


def print_stats(stats: dict):
    """Pretty print sync statistics"""
    print("\n" + "=" * 80)
    print("SYNC STATISTICS")
    print("=" * 80)
    print(f"Campaigns processed:    {stats['campaigns_processed']}")
    print(f"Campaigns inserted:     {stats['campaigns_inserted']}")
    print(f"Campaigns updated:      {stats['campaigns_updated']}")
    print(f"Participants inserted:  {stats['participants_inserted']}")
    print(f"Participants updated:   {stats['participants_updated']}")
    print(f"CSV files created:      {stats['csv_files_created']}")
    print(f"Errors:                 {stats['errors']}")

    if stats.get('start_time') and stats.get('end_time'):
        duration = (stats['end_time'] - stats['start_time']).total_seconds()
        print(f"Duration:               {duration:.1f} seconds")

    print("=" * 80 + "\n")


def show_database_stats(sync: CampaignSync):
    """Show MongoDB database statistics"""
    stats = sync.mongodb_writer.get_sync_statistics()

    print("\n" + "=" * 80)
    print("DATABASE STATISTICS")
    print("=" * 80)
    print(f"Total campaigns:        {stats['total_campaigns']}")
    print(f"Total participants:     {stats['total_participants']}")

    if stats['total_campaigns'] > 0:
        avg_participants = stats['total_participants'] / stats['total_campaigns']
        print(f"Avg participants/campaign: {avg_participants:.1f}")

    print("=" * 80 + "\n")

    # List CSV exports
    csv_files = sync.csv_writer.list_exports()
    print(f"CSV exports: {len(csv_files)} files in {sync.csv_writer.export_dir}")
    if csv_files:
        print("\nRecent exports:")
        for csv_file in csv_files[-5:]:  # Show last 5
            print(f"  - {csv_file}")


if __name__ == '__main__':
    main()

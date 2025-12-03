"""Command-line interface for octopus package"""
import sys
import argparse
from app import create_app


def main():
    """Main CLI entry point for octopus command"""
    parser = argparse.ArgumentParser(
        description='EmailOctopus Campaign Dashboard',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  octopus run                    # Run development server
  octopus run --host 0.0.0.0     # Run on all interfaces
  octopus run --port 8000        # Run on port 8000
  octopus shell                  # Open Python shell with app context
  octopus-create-user            # Create new user (separate command)

For more information, visit: https://github.com/empowersaves/octopus
        '''
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run the development server')
    run_parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
    )
    run_parser.add_argument(
        '--port',
        type=int,
        default=5006,
        help='Port to bind to (default: 5006)'
    )
    run_parser.add_argument(
        '--debug',
        action='store_true',
        default=True,
        help='Enable debug mode (default: True)'
    )
    run_parser.add_argument(
        '--no-debug',
        action='store_true',
        help='Disable debug mode'
    )

    # Shell command
    subparsers.add_parser('shell', help='Open Python shell with app context')

    # Init-db command
    subparsers.add_parser('init-db', help='Initialize database tables')

    # Version command
    subparsers.add_parser('version', help='Show version information')

    args = parser.parse_args()

    # Handle no command
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Execute commands
    if args.command == 'run':
        run_server(args)
    elif args.command == 'shell':
        open_shell()
    elif args.command == 'init-db':
        init_database()
    elif args.command == 'version':
        show_version()


def run_server(args):
    """Run the Flask development server"""
    app = create_app()

    debug = args.debug and not args.no_debug

    print("\n" + "="*60)
    print("EmailOctopus Campaign Dashboard - Development Server")
    print("="*60)
    print(f"Environment: {'Debug' if debug else 'Production'}")
    print(f"URL: http://{args.host}:{args.port}")
    print("Press CTRL+C to quit")
    print("="*60 + "\n")

    app.run(
        host=args.host,
        port=args.port,
        debug=debug
    )


def open_shell():
    """Open Python shell with app context"""
    import code
    from app import db
    from app.models.user import User

    app = create_app()

    with app.app_context():
        banner = """
EmailOctopus Dashboard - Interactive Shell
===========================================
Available objects:
  app   - Flask application instance
  db    - SQLAlchemy database instance
  User  - User model class

Example usage:
  >>> User.query.all()
  >>> user = User.query.first()
  >>> user.username
"""
        context = {
            'app': app,
            'db': db,
            'User': User,
        }

        code.interact(banner=banner, local=context)


def init_database():
    """Initialize database tables"""
    app = create_app()

    with app.app_context():
        from app import db

        print("\nInitializing database...")
        db.create_all()
        print("✓ Database tables created successfully!\n")
        print("Next step: Create a user with 'octopus-create-user'\n")


def show_version():
    """Show version information"""
    import flask
    import sqlalchemy
    import werkzeug

    print("\nEmailOctopus Campaign Dashboard")
    print("="*40)
    print("Version: 0.1.0")
    print("\nDependencies:")
    print(f"  Flask: {flask.__version__}")
    print(f"  SQLAlchemy: {sqlalchemy.__version__}")
    print(f"  Werkzeug: {werkzeug.__version__}")
    print()


if __name__ == '__main__':
    main()

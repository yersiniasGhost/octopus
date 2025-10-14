#!/usr/bin/env python3
"""Verify the application setup"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def verify_imports():
    """Verify all critical imports work"""
    print("\n" + "="*50)
    print("Verifying Application Setup")
    print("="*50 + "\n")

    checks_passed = 0
    checks_total = 0

    # Check Flask
    checks_total += 1
    try:
        import flask
        print(f"✓ Flask installed (version {flask.__version__})")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ Flask import failed: {e}")

    # Check SQLAlchemy
    checks_total += 1
    try:
        import flask_sqlalchemy
        print(f"✓ Flask-SQLAlchemy installed")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ Flask-SQLAlchemy import failed: {e}")

    # Check Flask-Login
    checks_total += 1
    try:
        import flask_login
        print(f"✓ Flask-Login installed")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ Flask-Login import failed: {e}")

    # Check Flask-WTF
    checks_total += 1
    try:
        import flask_wtf
        print(f"✓ Flask-WTF installed")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ Flask-WTF import failed: {e}")

    # Check envvars utility
    checks_total += 1
    try:
        from src.utils.envvars import EnvVars
        print(f"✓ EnvVars utility accessible")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ EnvVars import failed: {e}")

    # Check app creation
    checks_total += 1
    try:
        from app import create_app
        print(f"✓ Flask app factory accessible")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ App factory import failed: {e}")

    # Check User model
    checks_total += 1
    try:
        from app.models.user import User
        print(f"✓ User model accessible")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ User model import failed: {e}")

    # Check forms
    checks_total += 1
    try:
        from app.forms.auth_forms import LoginForm
        print(f"✓ Login form accessible")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ Login form import failed: {e}")

    # Check routes
    checks_total += 1
    try:
        from app.routes.auth import auth_bp
        from app.routes.main import main_bp
        print(f"✓ Route blueprints accessible")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ Route blueprints import failed: {e}")

    # Check dotenv
    checks_total += 1
    try:
        import dotenv
        print(f"✓ python-dotenv installed")
        checks_passed += 1
    except ImportError as e:
        print(f"✗ python-dotenv import failed: {e}")

    print("\n" + "="*50)
    print(f"Setup Check: {checks_passed}/{checks_total} passed")
    print("="*50 + "\n")

    if checks_passed == checks_total:
        print("✅ All checks passed! Your setup is ready.")
        print("\nNext steps:")
        print("1. Copy .env.example to .env and configure SECRET_KEY")
        print("2. Run: python3 scripts/create_user.py")
        print("3. Run: python3 run.py")
        print("4. Open: http://localhost:5000")
        return True
    else:
        print("❌ Some checks failed. Please install missing dependencies:")
        print("   pip install -r requirements.txt")
        return False


def check_env_file():
    """Check if .env file exists"""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        print("\n✓ .env file found")
    else:
        print("\n⚠ .env file not found. Copy .env.example to .env:")
        print("   cp .env.example .env")


def main():
    """Main verification"""
    success = verify_imports()
    check_env_file()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

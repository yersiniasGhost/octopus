#!/usr/bin/env python3
"""Script to create user accounts for the EmailOctopus dashboard"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models.user import User
from getpass import getpass


def create_user_interactive():
    """Create a user interactively"""
    print("\n" + "="*50)
    print("EmailOctopus Dashboard - Create User")
    print("="*50 + "\n")

    # Get user details
    username = input("Enter username: ").strip()
    if not username:
        print("Error: Username cannot be empty")
        return

    # Check if user already exists
    if User.query.filter_by(username=username).first():
        print(f"Error: User '{username}' already exists")
        return

    email = input("Enter email: ").strip()
    if not email:
        print("Error: Email cannot be empty")
        return

    # Check if email already exists
    if User.query.filter_by(email=email).first():
        print(f"Error: Email '{email}' is already registered")
        return

    full_name = input("Enter full name (optional): ").strip() or None

    # Get password securely
    password = getpass("Enter password: ")
    password_confirm = getpass("Confirm password: ")

    if password != password_confirm:
        print("Error: Passwords do not match")
        return

    if len(password) < 6:
        print("Error: Password must be at least 6 characters long")
        return

    # Create user
    try:
        user = User.create_user(
            username=username,
            email=email,
            password=password,
            full_name=full_name,
            created_by='admin'
        )
        print(f"\n✓ User '{username}' created successfully!")
        print(f"  ID: {user.id}")
        print(f"  Email: {user.email}")
        print(f"  Role: {user.role}")
        print(f"  Active: {user.is_active}")
        print()
    except Exception as e:
        print(f"Error creating user: {e}")
        db.session.rollback()


def list_users():
    """List all users"""
    users = User.query.all()
    if not users:
        print("\nNo users found in database.\n")
        return

    print("\n" + "="*70)
    print("Current Users")
    print("="*70)
    print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Active':<8}")
    print("-"*70)
    for user in users:
        print(f"{user.id:<5} {user.username:<20} {user.email:<30} {'Yes' if user.is_active else 'No':<8}")
    print("="*70 + "\n")


def main():
    """Main function"""
    app = create_app()

    with app.app_context():
        print("\nEmailOctopus Dashboard - User Management\n")
        print("1. Create new user")
        print("2. List all users")
        print("3. Exit")

        choice = input("\nEnter your choice (1-3): ").strip()

        if choice == '1':
            create_user_interactive()
        elif choice == '2':
            list_users()
        elif choice == '3':
            print("Goodbye!")
        else:
            print("Invalid choice")


if __name__ == '__main__':
    main()

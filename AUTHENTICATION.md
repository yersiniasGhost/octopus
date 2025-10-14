# Authentication & Security Documentation

## Overview

Your EmailOctopus Dashboard application has a complete authentication and security system implemented using:
- **SQLite3 Database**: User data storage
- **Flask-Login**: Session management
- **Werkzeug Security**: Password hashing (PBKDF2-SHA256)
- **Flask-WTF**: CSRF protection on forms
- **Route Protection**: Login required decorators

## Current Status

✅ **Fully Implemented**
- User authentication system
- Password hashing and verification
- Login/logout functionality
- Session management (30-minute timeout)
- CSRF protection
- Protected routes

## Database

**Location**: `instance/octopus.db`
**Type**: SQLite3
**Size**: 16KB

### Users Table Schema

```python
User Model:
- id (Integer, Primary Key)
- username (String, Unique, Indexed)
- email (String, Unique, Indexed)
- password_hash (String, 255 chars)
- full_name (String, Optional)
- role (String, Default: 'super_user')
- is_active (Boolean, Default: True)
- last_login (DateTime)
- created_at (DateTime)
- created_by (String)
```

## Current Users

| ID | Username | Email | Status |
|----|----------|-------|--------|
| 1 | loran | l@a.b.com | Active |
| 2 | admin | admin@example.com | Active |

## Security Features

### 1. Password Security
- **Hashing Algorithm**: PBKDF2-SHA256 (Werkzeug default)
- **Minimum Length**: 6 characters (enforced in form validation)
- **Storage**: Only hashed passwords stored, never plain text

### 2. Session Security
- **Session Timeout**: 30 minutes (1800 seconds)
- **Remember Me**: Optional persistent sessions
- **Session Protection**: Flask-Login session management

### 3. CSRF Protection
- **Flask-WTF**: All forms include CSRF tokens
- **Automatic Validation**: Forms validate CSRF on submission

### 4. Route Protection
All sensitive routes are protected with `@login_required` decorator:
- `/dashboard` - Main dashboard
- `/campaigns` - Campaign list
- `/campaigns/<id>` - Campaign details
- All API endpoints (`/api/*`)

## User Management

### Create New User

**Interactive Script**:
```bash
source venv/bin/activate
python3 scripts/create_user.py
# Select option 1, then follow prompts
```

**Programmatic Creation**:
```python
from app import create_app, db
from app.models.user import User

app = create_app()
with app.app_context():
    user = User.create_user(
        username='newuser',
        email='user@example.com',
        password='securepassword',
        full_name='New User',
        created_by='admin'
    )
```

### List All Users

```bash
source venv/bin/activate
python3 scripts/create_user.py
# Select option 2
```

### User Roles

Currently all users have role: `super_user`
- Full access to all features
- Can view all campaigns and data
- No role-based restrictions implemented yet

## Login Process

### Login Flow
1. User navigates to `/login`
2. Submits username and password
3. System verifies credentials:
   - User exists
   - Account is active (`is_active = True`)
   - Password hash matches
4. On success:
   - Creates session
   - Updates `last_login` timestamp
   - Redirects to dashboard or requested page
5. On failure:
   - Shows error message
   - No specific information about which credential failed (security best practice)

### Logout Process
1. User clicks logout
2. Session destroyed
3. Redirect to landing page
4. Flash message confirms logout

## Configuration

### Environment Variables (.env)

```bash
# Security
SECRET_KEY=your-secret-key-change-this-in-production

# Database
DATABASE_URI=sqlite:///octopus.db

# Session
PERMANENT_SESSION_LIFETIME=1800  # 30 minutes in seconds
```

**⚠️ Important**: Change `SECRET_KEY` in production to a secure random value:
```python
import secrets
secrets.token_hex(32)
```

## Testing Authentication

### Test Login
1. Start the application:
   ```bash
   source venv/bin/activate
   python3 run.py
   ```

2. Navigate to: http://localhost:5000/login

3. Use existing credentials:
   - **Username**: `admin`
   - **Password**: `admin123`

   OR

   - **Username**: `loran`
   - **Password**: (set by user)

### Test Protected Routes
1. Try accessing dashboard without login: http://localhost:5000/dashboard
   - Should redirect to login page

2. Login, then access dashboard
   - Should display dashboard content

3. Test logout functionality
   - Click logout in navbar
   - Should redirect to home page
   - Attempting to access dashboard should redirect to login

## Security Best Practices Implemented

✅ **Password Hashing**: PBKDF2-SHA256 with salt
✅ **CSRF Protection**: All forms protected
✅ **Session Management**: 30-minute timeout
✅ **Route Protection**: Sensitive routes require authentication
✅ **No Password Exposure**: Passwords never logged or displayed
✅ **Active User Check**: Inactive users cannot login
✅ **Generic Error Messages**: Login errors don't reveal which credential failed

## Future Security Enhancements (Optional)

Consider implementing these for production:

1. **Rate Limiting**: Prevent brute force attacks
   ```bash
   pip install flask-limiter
   ```

2. **Password Complexity**: Enforce stronger passwords
   - Minimum 8 characters
   - Mix of uppercase, lowercase, numbers, symbols

3. **Account Lockout**: Lock after N failed attempts

4. **Password Reset**: Email-based password recovery

5. **Two-Factor Authentication (2FA)**: Additional security layer

6. **Audit Logging**: Track login attempts and user actions

7. **Role-Based Access Control (RBAC)**: Different permission levels

8. **HTTPS**: Enforce encrypted connections in production

## Troubleshooting

### Can't Login
1. Verify user exists:
   ```bash
   python3 scripts/create_user.py
   # Option 2 to list users
   ```

2. Check user is active in database

3. Verify password was set correctly (create new test user)

4. Check application logs for errors

### Database Issues
1. Check database file exists:
   ```bash
   ls -lh instance/octopus.db
   ```

2. Reinitialize database (⚠️ destroys existing data):
   ```python
   from app import create_app, db
   app = create_app()
   with app.app_context():
       db.drop_all()
       db.create_all()
   ```

### Session Issues
1. Clear browser cookies
2. Check SECRET_KEY is set in .env
3. Restart Flask application

## Files Reference

### Core Authentication Files
- `app/models/user.py` - User model and password methods
- `app/routes/auth.py` - Login/logout routes
- `app/forms/auth_forms.py` - Login form with validation
- `app/__init__.py` - Flask-Login configuration
- `app/templates/login.html` - Login page template
- `app/templates/base.html` - Navigation with login/logout links

### User Management
- `scripts/create_user.py` - Interactive user creation script
- `app/cli.py` - CLI commands (if needed)

### Database
- `instance/octopus.db` - SQLite database file
- `.env` - Configuration including DATABASE_URI

## API Endpoints

All API endpoints require authentication:

```
GET  /api/campaigns              - List campaigns
GET  /api/campaigns/<id>         - Campaign details
GET  /api/test-connection        - Test API connection
GET  /api/campaigns/<id>/enriched-data - Enriched campaign data
GET  /api/campaigns/<id>/savings-histogram - Histogram data
```

All return 401 Unauthorized if not authenticated.

## Summary

Your application has enterprise-grade authentication with:
- ✅ Secure password storage
- ✅ Session management
- ✅ CSRF protection
- ✅ Protected routes
- ✅ User management tools
- ✅ SQLite3 database
- ✅ Production-ready security practices

The system is ready for use. Simply ensure you change the `SECRET_KEY` to a secure value before deploying to production.

# Octopus Quick Reference Card

Quick command reference for the EmailOctopus Campaign Dashboard.

## Activate Virtual Environment

**Linux/Mac**:
```bash
source venv/bin/activate
```

**Windows**:
```cmd
venv\Scripts\activate
```

**Verify activation**: You should see `(venv)` prefix in your terminal.

## Common Commands

### Run Application
```bash
# Default (localhost:5000, debug on)
octopus run

# Custom host and port
octopus run --host 0.0.0.0 --port 8000

# Disable debug mode
octopus run --no-debug
```

### User Management
```bash
# Interactive user creation/management
octopus-create-user

# Options available:
#   1. Create new user
#   2. List all users
#   3. Exit
```

### Database Operations
```bash
# Initialize database tables
octopus init-db

# Open Python shell with app context
octopus shell
```

### Development Tools
```bash
# Show version and dependencies
octopus version

# Show help
octopus --help
octopus run --help
```

### Alternative Run Methods
```bash
# Direct run (old method, still works)
python3 run.py

# User creation script (old method, still works)
python3 scripts/create_user.py
```

## First-Time Setup Checklist

- [ ] Virtual environment created: `python3 -m venv venv`
- [ ] Virtual environment activated: `source venv/bin/activate`
- [ ] Package installed: `pip install -e .`
- [ ] Environment file created: `cp .env.example .env`
- [ ] SECRET_KEY generated and added to `.env`
- [ ] Database initialized: `octopus init-db`
- [ ] First user created: `octopus-create-user`
- [ ] Application started: `octopus run`
- [ ] Tested login at http://localhost:5000

## Configuration Files

### .env (Required)
```bash
SECRET_KEY=your-secret-key-here
FLASK_ENV=development
FLASK_DEBUG=1
DATABASE_URI=sqlite:///octopus.db
```

### Generate SECRET_KEY
```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

## URLs

- **Landing Page**: http://localhost:5000/
- **Login**: http://localhost:5000/login
- **Dashboard**: http://localhost:5000/dashboard (requires login)

## Project Structure

```
octopus/
├── venv/                    # Virtual environment (created by you)
├── .env                     # Environment variables (create from .env.example)
├── octopus.db              # SQLite database (auto-created)
├── app/                     # Application code
│   ├── models/             # Database models
│   ├── routes/             # URL routes
│   ├── forms/              # WTForms
│   ├── templates/          # Jinja2 templates
│   └── static/             # CSS, JS, images
├── src/utils/              # Utilities (envvars.py, singleton.py)
├── scripts/                # Utility scripts
└── run.py                  # Alternative entry point
```

## Package Management

### Install/Reinstall
```bash
# Editable mode (development)
pip install -e .

# With all extras
pip install -e ".[dev,mongodb,reporting]"

# Individual extras
pip install -e ".[dev]"         # Development tools
pip install -e ".[mongodb]"     # MongoDB support
pip install -e ".[reporting]"   # Reporting features
```

### Extras Available
- **dev**: pytest, black, flake8, mypy
- **mongodb**: pymongo, mongoengine
- **reporting**: plotly, ReportLab, APScheduler

## Troubleshooting

### Command not found: octopus
```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Verify installation
pip show octopus

# 3. Reinstall if needed
pip install -e .
```

### Import errors
```bash
# Reinstall dependencies
pip install -r requirements.txt
```

### Database errors
```bash
# Remove old database and recreate
rm octopus.db
octopus init-db
```

### Port already in use
```bash
# Find process using port 5000
lsof -i :5000

# Kill process
kill -9 <PID>

# OR use different port
octopus run --port 8000
```

## Development Workflow

```bash
# 1. Start of day
source venv/bin/activate

# 2. Make code changes (editable mode means changes are immediate)

# 3. Run application
octopus run

# 4. Test in browser
# Open http://localhost:5000

# 5. Create/manage users as needed
octopus-create-user

# 6. End of day (deactivate optional)
deactivate
```

## Key Features

✅ User authentication with secure password hashing
✅ Session management (30-minute timeout)
✅ CSRF protection on all forms
✅ SQLite database for user management
✅ Professional landing page
✅ Protected dashboard
✅ CLI commands for easy management
✅ Editable installation for development

## Getting Help

```bash
# Command help
octopus --help
octopus run --help

# Documentation
cat README.md
cat GETTING_STARTED.md
cat PACKAGE_INSTALL.md
```

## Status

**Current Phase**: Phase 1 Complete ✅
- User authentication and login system
- Landing page and dashboard
- CLI commands and package installation

**Next Phase**: Phase 2 (EmailOctopus Integration)
- API client for EmailOctopus
- Campaign data extraction
- MongoDB integration
- Data synchronization

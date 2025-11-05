# Getting Started with Octopus

Complete guide to install and run the EmailOctopus Campaign Dashboard.

## Quick Installation (< 5 minutes)

### Step 1: Install Package

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install octopus package
pip install -e .
```

### Step 2: Configure

```bash
# Copy environment template
cp .env.example .env

# Generate SECRET_KEY
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

### Step 3: Initialize & Create User

```bash
# Initialize database
octopus init-db

# Create first user
octopus-create-user
```

### Step 4: Run

```bash
# Start server
octopus run

# Open browser → http://localhost:5000
```

**Done! 🎉**

---

## Detailed Installation

### System Requirements

- **Python**: 3.9 or higher
- **OS**: Linux, macOS, or Windows
- **RAM**: 512 MB minimum
- **Disk**: 100 MB

### Installation Options

#### Option A: Editable Package (Recommended for Development)

```bash
# Best for: Development, making changes to code
pip install -e .

# With all extras
pip install -e ".[dev,mongodb,reporting]"
```

**Benefits:**
- Changes to code take effect immediately
- No reinstall needed
- CLI commands work from anywhere

#### Option B: Regular Package

```bash
# Best for: Production, stable usage
pip install .

# With extras
pip install ".[mongodb,reporting]"
```

#### Option C: Dependencies Only

```bash
# Best for: Custom workflows, non-package usage
pip install -r requirements.txt
```

### Available Extras

| Extra | Contents | Install Command |
|-------|----------|-----------------|
| **dev** | pytest, black, flake8, mypy | `pip install -e ".[dev]"` |
| **mongodb** | pymongo, mongoengine | `pip install -e ".[mongodb]"` |
| **reporting** | plotly, ReportLab, APScheduler | `pip install -e ".[reporting]"` |
| **all** | Everything above | `pip install -e ".[dev,mongodb,reporting]"` |

---

## Configuration

### Environment Variables

Create `.env` file in project root:

```bash
# Flask Configuration
SECRET_KEY=<generate-with-secrets.token_hex(32)>
FLASK_ENV=development
FLASK_DEBUG=1

# Database
DATABASE_URI=sqlite:///octopus.db

# Session (optional)
PERMANENT_SESSION_LIFETIME=1800

# EmailOctopus (Phase 2)
# EMAILOCTOPUS_API_KEY=your-api-key-here
```

### Generate SECRET_KEY

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy output and add to `.env`:
```
SECRET_KEY=<your-generated-key-here>
```

---

## Database Setup

### Initialize Database

**Method 1: Using CLI (if package installed)**
```bash
octopus init-db
```

**Method 2: Automatic on First Run**
```bash
octopus run  # Creates database automatically
```

**Method 3: Manual Verification**
```bash
# Check if database exists
ls -la octopus.db

# If not, run once to create
python3 -c "from app import create_app; app = create_app(); app.app_context().push(); from app import db; db.create_all()"
```

### Database Location

Default: `octopus.db` in current directory

**Change location in `.env`:**
```
DATABASE_URI=sqlite:////absolute/path/to/octopus.db
```

---

## User Management

### Create Users

**Using CLI (recommended):**
```bash
octopus-create-user
```

**Or directly:**
```bash
python3 scripts/create_user.py
```

**Interactive prompts:**
1. Select option 1 (Create new user)
2. Enter username (e.g., `admin`)
3. Enter email (e.g., `admin@example.com`)
4. Enter full name (optional)
5. Enter password (minimum 6 characters)
6. Confirm password

### List Users

```bash
octopus-create-user
# Select option 2
```

### Example User Creation

```
Enter username: admin
Enter email: admin@example.com
Enter full name (optional): Admin User
Enter password: ******
Confirm password: ******

✓ User 'admin' created successfully!
  ID: 1
  Email: admin@example.com
  Role: super_user
  Active: True
```

---

## Running the Application

### Development Server

**Using CLI (recommended):**
```bash
# Default (localhost:5000, debug on)
octopus run

# Custom host/port
octopus run --host 0.0.0.0 --port 8000

# Disable debug
octopus run --no-debug
```

**Or directly:**
```bash
python3 run.py
```

### Server Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host to bind to | 127.0.0.1 |
| `--port` | Port to bind to | 5000 |
| `--debug` | Enable debug mode | True |
| `--no-debug` | Disable debug mode | - |

### Access the Application

Open browser and navigate to:
- **Local**: http://localhost:5000
- **Network**: http://your-ip:5000 (if using --host 0.0.0.0)

---

## Using the Application

### 1. Landing Page

Navigate to http://localhost:5000/

**Features:**
- Hero section with overview
- Feature cards
- Call-to-action buttons

### 2. Login

Click "Get Started" or navigate to `/login`

**Credentials:**
- Username: `admin` (or whatever you created)
- Password: Your password

**Features:**
- CSRF protection
- "Remember Me" option
- Session management (30-minute timeout)

### 3. Dashboard

After login, redirects to `/dashboard`

**Currently Shows:**
- User information card
- Placeholder stats (0 campaigns, 0 lists, 0 contacts)
- Coming soon message for EmailOctopus integration

### 4. Logout

Click username dropdown → Logout

---

## CLI Reference

### Main Command: `octopus`

```bash
# Show all commands
octopus --help

# Run development server
octopus run [--host HOST] [--port PORT] [--debug] [--no-debug]

# Interactive Python shell with app context
octopus shell

# Initialize database tables
octopus init-db

# Show version and dependencies
octopus version
```

### User Management: `octopus-create-user`

```bash
# Interactive user creation and management
octopus-create-user
```

### Interactive Shell

```bash
octopus shell
```

**Available objects:**
- `app` - Flask application instance
- `db` - SQLAlchemy database
- `User` - User model class

**Example usage in shell:**
```python
>>> User.query.all()
[<User admin>]

>>> user = User.query.first()
>>> user.username
'admin'

>>> user.email
'admin@example.com'
```

---

## Development Tools

### Code Formatting

```bash
# Install dev extras
pip install -e ".[dev]"

# Format code
black app/ src/ scripts/

# Check formatting
black --check app/ src/ scripts/
```

### Linting

```bash
# Lint code
flake8 app/ src/ scripts/

# With specific config
flake8 --config setup.cfg app/
```

### Type Checking

```bash
# Check types
mypy app/ src/ scripts/

# With config
mypy --config-file setup.cfg app/
```

### Testing

```bash
# Run tests (when available)
pytest

# With coverage
pytest --cov=app --cov-report=html

# View coverage
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## Verification

### Check Installation

```bash
# Verify octopus command
which octopus
# Expected: /path/to/venv/bin/octopus

# Check package info
pip show octopus
# Should show version 0.1.0

# Test import
python3 -c "from app import create_app; print('✓ OK')"

# List entry points
pip show -f octopus | grep bin
```

### Test Functionality

```bash
# 1. Version check
octopus version

# 2. Initialize database
octopus init-db

# 3. Check database exists
ls -la octopus.db

# 4. Create test user
octopus-create-user

# 5. Run server
octopus run

# 6. Open browser → http://localhost:5000
# 7. Login with created credentials
# 8. Verify dashboard loads
```

---

## Troubleshooting

### Command Not Found: `octopus`

**Problem:** Terminal says `octopus: command not found`

**Solutions:**
1. Activate virtual environment: `source venv/bin/activate`
2. Verify installation: `pip show octopus`
3. Reinstall: `pip install -e .`
4. Check PATH: `echo $PATH | grep venv`

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'app'`

**Solutions:**
1. Install package: `pip install -e .`
2. Check virtual environment is activated
3. Verify you're in project directory
4. Reinstall dependencies: `pip install -r requirements.txt`

### Database Errors

**Problem:** Database-related errors on startup

**Solutions:**
1. Initialize database: `octopus init-db`
2. Remove old database: `rm octopus.db`
3. Check permissions: `ls -la octopus.db`
4. Verify DATABASE_URI in `.env`

### Login Not Working

**Problem:** Can't log in with credentials

**Solutions:**
1. Verify user exists: `octopus-create-user` → option 2
2. Reset password: Create new user
3. Check Flask logs for errors
4. Verify SECRET_KEY in `.env`

### Port Already in Use

**Problem:** `Address already in use` error

**Solutions:**
1. Find process: `lsof -i :5000`
2. Kill process: `kill -9 <PID>`
3. Use different port: `octopus run --port 8000`

---

## What's Next?

### Immediate Next Steps

1. ✅ Explore the landing page
2. ✅ Test login/logout functionality
3. ✅ Create additional users if needed
4. ✅ Familiarize yourself with the dashboard

### Phase 2: EmailOctopus Integration

Coming soon:
- EmailOctopus API client
- Campaign data synchronization
- MongoDB integration
- Analytics and visualizations
- PDF report generation

### Contributing

This is an internal project. Contact your development team for:
- Feature requests
- Bug reports
- Contribution guidelines

---

## Additional Resources

- **README.md** - Comprehensive project documentation
- **QUICKSTART.md** - 5-minute quick start guide
- **PACKAGE_INSTALL.md** - Detailed package installation
- **INSTALLATION.md** - Step-by-step installation guide
- **IMPLEMENTATION_SUMMARY.md** - Technical implementation details
- **PIP_PACKAGE_SUMMARY.md** - Package conversion summary

---

## Support

For help:
1. Check documentation files listed above
2. Review troubleshooting section
3. Contact development team

---

**Welcome to Octopus! 🐙**

Your EmailOctopus Campaign Dashboard is ready to use!

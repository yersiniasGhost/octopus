# Package Installation Guide

## Installing as a Python Package

The `octopus` EmailOctopus Dashboard can be installed as a Python package using pip.

## Installation Methods

### Method 1: Development Installation (Editable)

**Recommended for active development**

```bash
# Navigate to project directory
cd /home/frich/devel/EmpowerSaves/octopus

# Install in editable mode
pip install -e .

# Or install with all extras
pip install -e ".[dev,mongodb,reporting]"
```

**Benefits:**
- Changes to code are immediately reflected
- No need to reinstall after modifications
- Perfect for development and testing

### Method 2: Regular Installation

**For production or stable usage**

```bash
# Install from local directory
pip install /home/frich/devel/EmpowerSaves/octopus

# Or install with extras
pip install "/home/frich/devel/EmpowerSaves/octopus[mongodb,reporting]"
```

### Method 3: From Git Repository (Future)

```bash
# Once hosted on GitHub
pip install git+https://github.com/empowersaves/octopus.git

# With extras
pip install "git+https://github.com/empowersaves/octopus.git#egg=octopus[mongodb,reporting]"
```

## Available Extras

The package supports optional dependency groups:

### Development Tools
```bash
pip install -e ".[dev]"
```
Includes:
- pytest (testing)
- pytest-cov (coverage)
- black (code formatting)
- flake8 (linting)
- mypy (type checking)

### MongoDB Support
```bash
pip install -e ".[mongodb]"
```
Includes:
- pymongo (MongoDB driver)
- mongoengine (ODM)

### Reporting Features
```bash
pip install -e ".[reporting]"
```
Includes:
- plotly (interactive charts)
- ReportLab (PDF generation)
- APScheduler (scheduled tasks)

### Install Everything
```bash
pip install -e ".[dev,mongodb,reporting]"
```

## After Installation

Once installed, the package provides command-line tools:

### 1. `octopus` - Main CLI

```bash
# Run development server
octopus run

# Run on specific host/port
octopus run --host 0.0.0.0 --port 8000

# Open interactive shell
octopus shell

# Initialize database
octopus init-db

# Show version
octopus version

# Help
octopus --help
```

### 2. `octopus-create-user` - User Management

```bash
# Create/manage users
octopus-create-user
```

## Quick Start After Installation

```bash
# 1. Install package in editable mode
pip install -e .

# 2. Set up environment
cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

# 3. Initialize database
octopus init-db

# 4. Create first user
octopus-create-user

# 5. Run application
octopus run

# 6. Open browser
# http://localhost:5000
```

## Verification

Check that installation worked:

```bash
# Verify octopus command is available
which octopus
# Should show: /path/to/venv/bin/octopus

# Check version
octopus version

# Verify Python can import the package
python -c "from app import create_app; print('✓ Import successful')"

# List installed package
pip show octopus
```

Expected output:
```
Name: octopus
Version: 0.1.0
Summary: EmailOctopus Campaign Analytics & Reporting Dashboard
Home-page: https://github.com/empowersaves/octopus
Author: EmpowerSaves
Author-email: dev@empowersaves.com
License: MIT
Location: /path/to/octopus
Requires: Flask, Flask-Login, Flask-SQLAlchemy, Flask-WTF, Werkzeug, email-validator, numpy, python-dotenv, requests
```

## Development Workflow

### Editable Installation Benefits

With `pip install -e .`, you can:

1. **Edit code directly** - Changes take effect immediately
2. **Use CLI commands** - `octopus` command always available
3. **Import anywhere** - `from app import create_app` works globally
4. **Run tests** - `pytest` finds your code automatically

### Common Development Tasks

```bash
# Format code
black app/ src/ scripts/

# Lint code
flake8 app/ src/ scripts/

# Type check
mypy app/ src/ scripts/

# Run tests
pytest

# Run tests with coverage
pytest --cov=app --cov-report=html

# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Uninstallation

```bash
# Uninstall package
pip uninstall octopus

# Confirm removal
pip show octopus  # Should show nothing
```

## Updating the Package

After making changes:

### If installed in editable mode (`-e`)
No action needed! Changes are automatically reflected.

### If installed normally
```bash
# Reinstall
pip install --upgrade /path/to/octopus

# Or force reinstall
pip install --force-reinstall /path/to/octopus
```

## Package Structure

After installation, the package structure is:

```
octopus/
├── app/                    # Main application package
│   ├── __init__.py
│   ├── cli.py             # CLI entry point
│   ├── models/            # Database models
│   ├── routes/            # Flask routes
│   ├── forms/             # WTForms
│   ├── templates/         # Jinja2 templates
│   └── static/            # Static assets
├── src/                   # Utilities
│   └── utils/
│       ├── envvars.py
│       └── singleton.py
└── scripts/               # Management scripts
    └── create_user.py
```

## Distribution

### Building Distribution Packages

```bash
# Install build tools
pip install build

# Build source and wheel distributions
python -m build

# Creates:
# dist/octopus-0.1.0.tar.gz (source)
# dist/octopus-0.1.0-py3-none-any.whl (wheel)
```

### Installing from Built Distribution

```bash
# From wheel
pip install dist/octopus-0.1.0-py3-none-any.whl

# From source tarball
pip install dist/octopus-0.1.0.tar.gz
```

## Troubleshooting

### Command not found: `octopus`

**Problem:** After installation, `octopus` command not available

**Solutions:**
1. Ensure virtual environment is activated
2. Check installation: `pip show octopus`
3. Reinstall: `pip install -e .`
4. Verify PATH: `echo $PATH | grep venv`

### Import errors after installation

**Problem:** `ModuleNotFoundError: No module named 'app'`

**Solutions:**
1. Check installation: `pip list | grep octopus`
2. Verify you're in correct virtual environment
3. Reinstall in editable mode: `pip install -e .`

### Templates/static files not found

**Problem:** 404 errors for static files or template errors

**Solutions:**
1. Ensure `MANIFEST.in` includes templates and static files
2. Reinstall package: `pip install -e .`
3. Check `setup.py` includes `include_package_data=True`

### Database file location

**Problem:** `octopus.db` created in wrong location

**Solution:**
The database is created in the current working directory. To control location:
1. Set `DATABASE_URI` in `.env`: `sqlite:////absolute/path/to/octopus.db`
2. Always run from project directory
3. Or use absolute path in environment variable

## Advanced Configuration

### Custom Installation Location

```bash
# Install to specific location
pip install -e . --target /custom/path

# Set PYTHONPATH
export PYTHONPATH=/custom/path:$PYTHONPATH
```

### Production Installation

For production deployment:

```bash
# Create production virtual environment
python3 -m venv /opt/octopus/venv

# Activate
source /opt/octopus/venv/bin/activate

# Install production dependencies only
pip install /path/to/octopus

# No dev dependencies
pip show octopus | grep Requires
# Should NOT include pytest, black, etc.
```

## Next Steps

After successful installation:

1. ✅ Verify installation with `octopus version`
2. ✅ Configure environment (`.env` file)
3. ✅ Initialize database with `octopus init-db`
4. ✅ Create users with `octopus-create-user`
5. ✅ Run application with `octopus run`

For detailed usage, see:
- `README.md` - Comprehensive documentation
- `QUICKSTART.md` - Quick start guide
- `INSTALLATION.md` - Detailed installation instructions

---

**You're now ready to use octopus as a proper Python package! 🎉**

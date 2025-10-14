# Quick Start Guide

## Get Up and Running in 5 Minutes

### Step 1: Install Package

**Option A: Install as Package (Recommended)**
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode
pip install -e .
```

**Option B: Install Dependencies Only**
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Generate SECRET_KEY
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

Edit `.env` and ensure it contains:
```
SECRET_KEY=<generated-key-from-above>
FLASK_ENV=development
FLASK_DEBUG=1
DATABASE_URI=sqlite:///octopus.db
```

### Step 3: Create Your First User

**If installed as package:**
```bash
octopus-create-user
```

**Or run directly:**
```bash
python3 scripts/create_user.py
```

Select option 1 and enter:
- Username: admin
- Email: admin@example.com
- Full name: Admin User
- Password: <your-secure-password>
- Confirm password: <same-password>

### Step 4: Run the Application

**If installed as package:**
```bash
octopus run
```

**Or run directly:**
```bash
python3 run.py
```

Open your browser to: **http://localhost:5000**

### Step 5: Login

1. Click "Get Started" or "Login"
2. Enter your username and password
3. Access the dashboard!

## What You Can Do Now

✅ **Landing Page** (`/`) - Public welcome page
✅ **Login System** (`/login`) - Secure authentication
✅ **Dashboard** (`/dashboard`) - Protected user area
✅ **User Management** - Create/list users via script

## Next Steps

After Phase 1, you'll add:
- EmailOctopus API integration
- Campaign data synchronization
- MongoDB for campaign storage
- Analytics and reporting features

## Troubleshooting

**Can't import `envvars`?**
- Ensure `src/utils/envvars.py` exists (you mentioned adding this manually)
- Check that `src/utils/` has `__init__.py`

**Database errors?**
```bash
rm octopus.db  # Remove old database
python3 run.py  # Recreates database
```

**Import errors?**
```bash
pip install -r requirements.txt  # Reinstall dependencies
```

## Support

Contact your development team for assistance.

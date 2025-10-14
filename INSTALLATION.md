# Installation & First Run

## Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Git (optional, for version control)

## Installation Steps

### 1. Create Virtual Environment

```bash
# Navigate to project directory
cd /home/frich/devel/EmpowerSaves/octopus

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Expected output:**
```
Successfully installed Flask-3.0.0 Flask-Login-0.6.3 Flask-SQLAlchemy-3.1.1
Flask-WTF-1.2.1 Werkzeug-3.0.1 email-validator-2.1.0 numpy-1.26.3
python-dotenv-1.0.0 requests-2.31.0
```

### 3. Verify Installation

```bash
python3 scripts/verify_setup.py
```

**Expected output:**
```
==================================================
Verifying Application Setup
==================================================

✓ Flask installed (version 3.0.0)
✓ Flask-SQLAlchemy installed
✓ Flask-Login installed
✓ Flask-WTF installed
✓ EnvVars utility accessible
✓ Flask app factory accessible
✓ User model accessible
✓ Login form accessible
✓ Route blueprints accessible
✓ python-dotenv installed

==================================================
Setup Check: 10/10 passed
==================================================

✅ All checks passed! Your setup is ready.
```

### 4. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Generate secure SECRET_KEY
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

**Verify .env contents:**
```bash
cat .env
```

Should contain:
```
SECRET_KEY=<your-generated-key>
FLASK_ENV=development
FLASK_DEBUG=1
DATABASE_URI=sqlite:///octopus.db
```

### 5. Create Your First User

```bash
python3 scripts/create_user.py
```

**Interactive prompts:**
```
EmailOctopus Dashboard - User Management

1. Create new user
2. List all users
3. Exit

Enter your choice (1-3): 1

==================================================
EmailOctopus Dashboard - Create User
==================================================

Enter username: admin
Enter email: admin@example.com
Enter full name (optional): Admin User
Enter password: [hidden]
Confirm password: [hidden]

✓ User 'admin' created successfully!
  ID: 1
  Email: admin@example.com
  Role: super_user
  Active: True
```

### 6. Run the Application

```bash
python3 run.py
```

**Expected output:**
```
Loading .env from local directory: /home/frich/devel/EmpowerSaves/octopus/.env
 * Serving Flask app 'app'
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://<your-ip>:5000
Press CTRL+C to quit
 * Restarting with stat
 * Debugger is active!
```

### 7. Access the Application

Open your browser and navigate to:
- **Landing Page**: http://localhost:5000/
- **Login Page**: http://localhost:5000/login
- **Dashboard** (after login): http://localhost:5000/dashboard

## First Login

1. Navigate to http://localhost:5000/login
2. Enter credentials:
   - **Username**: admin (or whatever you created)
   - **Password**: [your password]
3. Click "Login"
4. You should be redirected to the dashboard

## Verification Checklist

- [ ] Virtual environment created and activated
- [ ] All dependencies installed successfully
- [ ] `verify_setup.py` shows 10/10 checks passed
- [ ] `.env` file created with SECRET_KEY
- [ ] At least one user account created
- [ ] Application runs without errors on http://localhost:5000
- [ ] Landing page displays correctly
- [ ] Login page displays correctly
- [ ] Can log in successfully
- [ ] Dashboard displays after login
- [ ] Can log out successfully

## Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'flask'`

**Solution:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### EnvVars Import Error

**Problem:** `ImportError: cannot import name 'get_env' from 'src.utils.envvars'`

**Solution:** The code uses `EnvVars` class, not `get_env` function. This is correct and should work.

### Database Errors

**Problem:** Database-related errors on startup

**Solution:**
```bash
# Remove existing database
rm octopus.db

# Restart application (will recreate database)
python3 run.py
```

### Port Already in Use

**Problem:** `Address already in use`

**Solution:**
```bash
# Find process using port 5000
lsof -i :5000

# Kill the process
kill -9 <PID>

# Or run on different port
# Edit run.py and change port=5000 to port=5001
```

### SECRET_KEY Error

**Problem:** `RuntimeError: The session is unavailable because no secret key was set`

**Solution:**
```bash
# Ensure .env file exists
ls -la .env

# Verify SECRET_KEY is set
cat .env | grep SECRET_KEY

# If missing, generate one:
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

### Login Not Working

**Problem:** Login form submits but nothing happens

**Solutions:**
1. Check if user exists: `python3 scripts/create_user.py` → Option 2
2. Verify password is correct
3. Check Flask console for error messages
4. Ensure CSRF token is generated (check browser console)

## Next Steps After Installation

1. **Explore the Application**
   - Visit landing page
   - Log in and explore dashboard
   - Test logout functionality

2. **Create Additional Users** (if needed)
   - Run `python3 scripts/create_user.py`
   - Create second super user account

3. **Customize** (optional)
   - Edit `app/static/css/style.css` for styling
   - Modify templates in `app/templates/`

4. **Prepare for Phase 2**
   - Set up MongoDB (local or Atlas)
   - Get EmailOctopus API key
   - Add to `.env` file

## Production Deployment (Future)

For production deployment to AWS:

1. Use a production-grade WSGI server (Gunicorn, uWSGI)
2. Set `FLASK_ENV=production` and `FLASK_DEBUG=0`
3. Generate a secure SECRET_KEY (different from dev)
4. Use HTTPS/SSL certificates
5. Configure proper logging
6. Set up database backups
7. Use environment-specific `.env` files

See `README.md` for detailed production deployment instructions.

## Support

If you encounter issues not covered here:
- Check `README.md` for detailed documentation
- Review `QUICKSTART.md` for quick reference
- Check Flask logs in terminal for error messages
- Verify all files are in correct locations per project structure

---

**Congratulations! Your EmailOctopus Dashboard is now running! 🎉**

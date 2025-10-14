# Troubleshooting Guide

Common issues and solutions for the Octopus application.

## Campaign Detail Page Errors

### Issue: "TypeError: unsupported operand type(s) for /: 'dict' and 'int'"

**Symptoms**:
- Error when clicking "View Details" on a campaign
- Template rendering fails with type error
- Traceback shows error in `campaigns/detail.html` line 97

**Root Cause**:
The EmailOctopus API may return nested data structures for campaign statistics instead of simple integers.

**Solution Applied** (Fixed in latest version):
- Template now uses type checking with `is number` test
- Safe defaults (0) for non-numeric values
- Variables set once and reused for calculations
- Debug logging added to see actual API response

**If error persists**:
1. Check application logs for debug output showing report structure
2. Look for lines like: `Reports structure: {...}`
3. Verify the API response format matches expected structure

**Manual Fix** (if needed):
```jinja2
{# Old (error-prone) #}
{{ reports.opened / reports.sent * 100 }}

{# New (safe) #}
{% set opened_count = reports.opened if reports.opened is number else 0 %}
{% set sent_count = reports.sent if reports.sent is number else 0 %}
{{ (opened_count / sent_count * 100) if sent_count > 0 else 0 }}
```

## API Connection Issues

### Issue: "Invalid API key or unauthorized access"

**Symptoms**:
- Cannot view campaigns
- Error message about authentication
- API test connection fails

**Solutions**:
1. Verify API key in `.env`:
   ```bash
   cat .env | grep EMAILOCTOPUS_API_KEY
   ```

2. Check for extra spaces or quotes:
   ```bash
   # Correct
   EMAILOCTOPUS_API_KEY=abc123def456

   # Wrong
   EMAILOCTOPUS_API_KEY="abc123def456"  # No quotes
   EMAILOCTOPUS_API_KEY= abc123def456   # No spaces
   ```

3. Get new API key:
   - Visit: https://emailoctopus.com/api-documentation
   - Generate new key
   - Update `.env`
   - Restart application

4. Restart application after changing `.env`:
   ```bash
   # Stop server (Ctrl+C)
   octopus run
   ```

### Issue: "API rate limit exceeded"

**Symptoms**:
- Error after multiple requests
- 429 HTTP status code
- Temporary inability to access campaigns

**Solutions**:
1. Wait a few minutes before retrying
2. Reduce frequency of API calls
3. Future: Implement caching (Phase 2)

## Installation Issues

### Issue: Command not found: octopus

**Symptoms**:
- Terminal says `octopus: command not found`
- CLI commands don't work

**Solutions**:
1. Activate virtual environment:
   ```bash
   source venv/bin/activate
   ```

2. Verify installation:
   ```bash
   pip show octopus
   which octopus
   ```

3. Reinstall if needed:
   ```bash
   pip install -e .
   ```

### Issue: Import errors

**Symptoms**:
- `ModuleNotFoundError`
- Application won't start

**Solutions**:
1. Activate virtual environment
2. Reinstall dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Verify package installed:
   ```bash
   pip list | grep -i flask
   pip list | grep -i octopus
   ```

## Database Issues

### Issue: Database errors on startup

**Symptoms**:
- SQLite errors
- Database locked messages
- Missing tables

**Solutions**:
1. Initialize database:
   ```bash
   octopus init-db
   ```

2. Remove and recreate:
   ```bash
   rm octopus.db
   octopus init-db
   ```

3. Check permissions:
   ```bash
   ls -la octopus.db
   ```

## Login Issues

### Issue: Can't log in with credentials

**Symptoms**:
- Invalid username/password message
- Login form keeps reappearing

**Solutions**:
1. Verify user exists:
   ```bash
   octopus-create-user
   # Select option 2 to list users
   ```

2. Create new user:
   ```bash
   octopus-create-user
   # Select option 1
   ```

3. Check database:
   ```bash
   octopus shell
   ```
   ```python
   from app.models.user import User
   User.query.all()
   ```

4. Verify SECRET_KEY in `.env`:
   ```bash
   grep SECRET_KEY .env
   ```

## Port Already in Use

### Issue: "Address already in use" error

**Symptoms**:
- Can't start application
- Port 5000 occupied
- OSError: [Errno 98]

**Solutions**:
1. Find process using port:
   ```bash
   lsof -i :5000
   ```

2. Kill process:
   ```bash
   kill -9 <PID>
   ```

3. Use different port:
   ```bash
   octopus run --port 8000
   ```

## Template Rendering Issues

### General Template Errors

**Debug steps**:
1. Check Flask debug mode enabled:
   ```bash
   grep FLASK_DEBUG .env
   # Should show: FLASK_DEBUG=1
   ```

2. Check application logs:
   ```bash
   # Logs appear in terminal when running
   octopus run
   ```

3. Enable detailed logging:
   ```python
   # In app/__init__.py (temporary)
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

## API Client Issues

### Debugging API Calls

**Enable debug logging**:
```python
# Run in octopus shell
import logging
logging.basicConfig(level=logging.DEBUG)

from app.services import EmailOctopusClient
client = EmailOctopusClient()
campaigns = client.get_campaigns(limit=1)
```

**Check API response structure**:
```python
# In octopus shell
from app.services import EmailOctopusClient
client = EmailOctopusClient()

# Get campaign
campaigns = client.get_campaigns(limit=1)
print("Campaigns:", campaigns)

# Get reports
if campaigns['data']:
    campaign_id = campaigns['data'][0]['id']
    reports = client.get_campaign_reports(campaign_id)
    print("Reports:", reports)
    print("Report keys:", reports.keys())
    for key, value in reports.items():
        print(f"  {key}: {value} (type: {type(value)})")
```

## Common Error Messages

### "No module named 'app'"

**Solution**: Install package
```bash
pip install -e .
```

### "SECRET_KEY not found"

**Solution**: Create `.env` from example
```bash
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

### "No campaigns found"

**Not an error** - means EmailOctopus account has no campaigns
- Create test campaign in EmailOctopus
- Refresh page

## Getting Help

### Check Logs

1. **Application logs**: Appear in terminal where `octopus run` is running
2. **Flask debug page**: Shows detailed error if `FLASK_DEBUG=1`
3. **Python shell**: Use `octopus shell` to debug interactively

### Debug Checklist

- [ ] Virtual environment activated?
- [ ] `.env` file exists with all required variables?
- [ ] Database initialized (`octopus init-db`)?
- [ ] User created (`octopus-create-user`)?
- [ ] API key valid in `.env`?
- [ ] Application running (`octopus run`)?
- [ ] Checked logs for errors?

### Collect Information

When reporting issues, include:
1. Error message (full traceback)
2. Steps to reproduce
3. Environment info:
   ```bash
   python --version
   pip show octopus
   cat .env.example  # Don't share actual .env!
   ```
4. Application logs

## Quick Fixes Summary

| Issue | Quick Fix |
|-------|-----------|
| Template errors | Restart application |
| API errors | Check `.env` API key |
| Can't login | Create user with `octopus-create-user` |
| Port in use | Use `octopus run --port 8000` |
| Import errors | `pip install -e .` |
| Database errors | `rm octopus.db && octopus init-db` |
| Command not found | `source venv/bin/activate` |

## Prevention

### Best Practices

1. **Always activate virtual environment** before running commands
2. **Don't commit `.env`** - it's in `.gitignore`
3. **Keep dependencies updated**: `pip install --upgrade -e .`
4. **Check logs** when something goes wrong
5. **Use test script**: `python3 scripts/test_emailoctopus.py`

### Regular Maintenance

```bash
# Weekly
pip install --upgrade pip setuptools wheel

# After pulling updates
pip install -e .
octopus init-db  # If database schema changed

# Before reporting issues
python3 scripts/test_emailoctopus.py
```

---

**Last Updated**: October 7, 2025
**Status**: Active maintenance

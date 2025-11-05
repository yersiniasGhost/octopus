# Flask Configuration Guide

## Environment Variable Configuration

The Flask application now uses environment variables for all configuration settings through the `EnvVars()` class.

## Available Configuration Variables

### Flask Server Settings

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `FLASK_HOST` | Host to bind Flask server | `0.0.0.0` | `127.0.0.1`, `0.0.0.0` |
| `FLASK_PORT` | Port number for Flask server | `5000` | `5000`, `8080`, `3000` |
| `FLASK_DEBUG` | Enable debug mode | `True` | `True`, `False`, `1`, `0` |
| `FLASK_ENV` | Flask environment | `development` | `development`, `production` |

### Security Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SECRET_KEY` | Flask session secret key | `dev-secret-key-change-in-production` | ✅ Yes |

### Database Settings

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `DATABASE_URI` | SQLAlchemy database URI | `sqlite:///octopus.db` | `sqlite:///octopus.db` |

### Session Settings

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `PERMANENT_SESSION_LIFETIME` | Session timeout in seconds | `1800` | `1800` (30 min) |

### EmailOctopus API Settings

| Variable | Description | Required |
|----------|-------------|----------|
| `EMAILOCTOPUS_API_KEY` | Your EmailOctopus API key | ✅ Yes |
| `EMAILOCTOPUS_API_BASE_URL` | API base URL | Optional |

### MongoDB Settings

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `MONGODB_HOST` | MongoDB host | `localhost` | `localhost`, `192.168.1.100` |
| `MONGODB_PORT` | MongoDB port | `27017` | `27017` |
| `MONGODB_DATABASE` | MongoDB database name | `emailoctopus_db` | `emailoctopus_db` |

## Usage Examples

### Change Flask Port

**Option 1: Edit .env file**
```bash
FLASK_PORT=8080
```

**Option 2: Command line**
```bash
FLASK_PORT=8080 python3 run.py
```

### Run on Different Host

```bash
# Localhost only (more secure for development)
FLASK_HOST=127.0.0.1 python3 run.py

# All interfaces (accessible from network)
FLASK_HOST=0.0.0.0 python3 run.py
```

### Production Configuration

Create a production `.env` file:

```bash
# Flask Configuration
SECRET_KEY=<generate-with-secrets.token_hex(32)>
FLASK_HOST=0.0.0.0
FLASK_PORT=8000
FLASK_DEBUG=0
FLASK_ENV=production

# Database Configuration
DATABASE_URI=sqlite:///octopus.db

# Session Configuration
PERMANENT_SESSION_LIFETIME=1800

# EmailOctopus API Configuration
EMAILOCTOPUS_API_KEY=<your-production-api-key>
EMAILOCTOPUS_API_BASE_URL=https://emailoctopus.com/api/1.6

# MongoDB Configuration
MONGODB_HOST=<production-mongodb-host>
MONGODB_PORT=27017
MONGODB_DATABASE=emailoctopus_production
```

### Generate Secure SECRET_KEY

```python
import secrets
print(secrets.token_hex(32))
# Output: 'a1b2c3d4e5f6...' (64 character hex string)
```

## Implementation Details

### run.py

The application entry point reads configuration from environment variables:

```python
from src.utils.envvars import EnvVars

env = EnvVars()
port = int(env.get_env('FLASK_PORT', '5000'))
host = env.get_env('FLASK_HOST', '0.0.0.0')
debug = env.get_bool('FLASK_DEBUG', 'True')

app.run(debug=debug, host=host, port=port)
```

### EnvVars Class

The `EnvVars` class loads environment variables from:
1. Local `.env` file (project directory) - **Priority**
2. Home directory `.env` file (`~/.env`) - Fallback
3. System environment variables - Final fallback
4. Default values specified in code

### Environment Variable Types

**String Variables**: Use `get_env()`
```python
host = env.get_env('FLASK_HOST', '0.0.0.0')
```

**Boolean Variables**: Use `get_bool()`
```python
debug = env.get_bool('FLASK_DEBUG', 'True')
# Accepts: 'true', '1', 'yes', 'y', True
```

**Integer Variables**: Cast with `int()`
```python
port = int(env.get_env('FLASK_PORT', '5000'))
```

## Testing Configuration

### Verify Current Configuration

```bash
source venv/bin/activate
python3 -c "
from src.utils.envvars import EnvVars
env = EnvVars()
print(f'Host: {env.get_env(\"FLASK_HOST\", \"0.0.0.0\")}')
print(f'Port: {env.get_env(\"FLASK_PORT\", \"5000\")}')
print(f'Debug: {env.get_bool(\"FLASK_DEBUG\", \"True\")}')
print(f'Secret Key Set: {bool(env.get_env(\"SECRET_KEY\"))}')
"
```

### Test Different Ports

```bash
# Terminal 1 - Default port (5000)
python3 run.py

# Terminal 2 - Custom port (8080)
FLASK_PORT=8080 python3 run.py

# Terminal 3 - Another custom port (3000)
FLASK_PORT=3000 python3 run.py
```

## Troubleshooting

### Port Already in Use

```bash
# Find what's using the port
sudo lsof -i :5000

# Kill the process
kill -9 <PID>

# Or use a different port
FLASK_PORT=5001 python3 run.py
```

### Configuration Not Loading

1. Check .env file exists:
   ```bash
   ls -la .env
   ```

2. Verify .env file format (no quotes needed):
   ```bash
   FLASK_PORT=5000
   # NOT: FLASK_PORT="5000"
   ```

3. Check for typos in variable names

4. Restart application after changes

### Debug Mode Issues

If debug mode doesn't work:
```bash
# Explicitly enable
FLASK_DEBUG=1 python3 run.py

# Or disable
FLASK_DEBUG=0 python3 run.py
```

## Best Practices

### Development
- ✅ Use `FLASK_DEBUG=1` for automatic reloading
- ✅ Use `FLASK_HOST=127.0.0.1` for local-only access
- ✅ Keep default port `5000` for consistency
- ✅ Use test SECRET_KEY for development

### Production
- ✅ Set `FLASK_DEBUG=0` to disable debug mode
- ✅ Use strong SECRET_KEY (64+ characters)
- ✅ Consider using a production WSGI server (Gunicorn, uWSGI)
- ✅ Use environment-specific .env files
- ✅ Never commit .env files to version control

### Security
- ⚠️ Never expose debug mode in production
- ⚠️ Always use HTTPS in production
- ⚠️ Keep SECRET_KEY secret and unique per environment
- ⚠️ Restrict FLASK_HOST in production if needed

## Production Deployment

For production, consider using Gunicorn instead of Flask's development server:

```bash
# Install Gunicorn
pip install gunicorn

# Run with Gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 'app:create_app()'
```

Or create a systemd service:

```ini
[Unit]
Description=EmailOctopus Dashboard
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/octopus
Environment="PATH=/path/to/octopus/venv/bin"
EnvironmentFile=/path/to/octopus/.env
ExecStart=/path/to/octopus/venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 'app:create_app()'

[Install]
WantedBy=multi-user.target
```

## Summary

✅ Flask now uses environment variables for all configuration
✅ Port, host, and debug mode are configurable via .env
✅ Defaults are sensible for development
✅ Easy to customize for different environments
✅ Production-ready with proper secret management

Change port by setting `FLASK_PORT` in your `.env` file or environment variables.

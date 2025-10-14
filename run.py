#!/usr/bin/env python3
"""Application entry point"""
from app import create_app
from src.utils.envvars import EnvVars

app = create_app()

if __name__ == '__main__':
    env = EnvVars()
    port = int(env.get_env('FLASK_PORT', '5000'))
    host = env.get_env('FLASK_HOST', '0.0.0.0')
    debug = env.get_bool('FLASK_DEBUG', 'True')

    app.run(debug=debug, host=host, port=port)

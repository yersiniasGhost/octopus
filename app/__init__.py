"""Flask application factory"""
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)

    # Load configuration from environment variables
    from src.utils.envvars import EnvVars
    env = EnvVars()

    app.config['SECRET_KEY'] = env.get_env('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = env.get_env('DATABASE_URI', 'sqlite:///octopus.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'

    # Import and register blueprints
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.campaigns import campaigns_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(campaigns_bp)

    # Create database tables
    with app.app_context():
        db.create_all()

    return app


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    from app.models.user import User
    return User.query.get(int(user_id))

"""Authentication routes"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.forms.auth_forms import LoginForm

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login route"""
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()

    if form.validate_on_submit():
        # Find user by username
        user = User.query.filter_by(username=form.username.data).first()

        # Verify user exists and password is correct
        if user and user.is_active and user.check_password(form.password.data):
            # Log the user in
            login_user(user, remember=form.remember.data)

            # Update last login timestamp
            user.update_last_login()

            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.dashboard'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')

    return render_template('login.html', form=form, title='Login')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout route"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.index'))

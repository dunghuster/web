from flask import session
from models import User

def get_current_user():
    return User.query.get(session.get('user_id')) if session.get('user_id') else None

def can_access_panel(user: User):
    return bool(user and (user.is_admin or user.is_staff))

def is_admin_only(user: User):
    return bool(user and user.is_admin)

def is_staff_user(user: User):
    return bool(user and (user.is_admin or user.is_staff))
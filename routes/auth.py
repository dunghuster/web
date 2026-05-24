from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from models import User

# Khởi tạo Blueprint cho tính năng Auth
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip()
        password = data.get('password') or ''

        if not username or not email or not password:
            return jsonify({'error': 'Thiếu thông tin'}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'User tồn tại'}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email tồn tại'}), 400

        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            is_admin=False,
            is_staff=False
        )
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        return jsonify({'success': True}), 200

    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return jsonify({'success': True, 'is_admin': user.is_admin, 'is_staff': user.is_staff}), 200
        return jsonify({'error': 'Sai thông tin'}), 401

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('auth.login')) # Chú ý: đã đổi url_for thành 'auth.login'

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        data = request.get_json() or {}
        if data.get('action') == 'change_password':
            if not check_password_hash(user.password, data.get('old_password', '')):
                return jsonify({'error': 'Mật khẩu cũ không đúng'}), 400
            user.password = generate_password_hash(data.get('new_password', ''))
        elif data.get('action') == 'update_info':
            email = (data.get('email') or '').strip()
            if not email:
                return jsonify({'error': 'Email không hợp lệ'}), 400
            user.email = email

        db.session.commit()
        return jsonify({'success': True}), 200

    return render_template('profile.html', user=user)
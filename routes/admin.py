from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.orm import joinedload
from extensions import db
from models import User, Article, FeedbackPost
from utils import get_current_user, can_access_panel, is_admin_only

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
def admin_dashboard():
    user = get_current_user()
    if not can_access_panel(user):
        return "Access denied", 403

    # TỐI ƯU HIỆU NĂNG: Thêm joinedload(FeedbackPost.user)
    fb_q = FeedbackPost.query.options(joinedload(FeedbackPost.user)).order_by(
        db.case(
            (FeedbackPost.status == 'pending', 0),
            (FeedbackPost.status == 'approved', 1),
            else_=2
        ),
        FeedbackPost.created_at.desc()
    ).all()

    # TỐI ƯU HIỆU NĂNG: Thêm joinedload(Article.author)
    articles_q = Article.query.options(joinedload(Article.author)).order_by(Article.created_at.desc()).all()

    return render_template(
        'admin.html',
        articles=articles_q,
        feedbacks=fb_q,
        current_user=user
    )

@admin_bp.route('/api/article/create', methods=['POST'])
def create_article():
    user = get_current_user()
    if not can_access_panel(user):
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = data.get('content') or ''
    category = (data.get('category') or '').strip()

    if not title or not content or not category:
        return jsonify({'error': 'Thiếu dữ liệu'}), 400

    article = Article(
        title=title,
        content=content,
        category=category,
        author_id=user.id,
        priority=int(data.get('priority', 0)),
        is_published=bool(data.get('is_published', True))
    )
    db.session.add(article)
    db.session.commit()
    return jsonify({'success': True}), 201
@admin_bp.route('/api/article/<int:article_id>', methods=['GET'])
def get_article(article_id):
    user = get_current_user()
    if not can_access_panel(user):
        return jsonify({'error': 'Access denied'}), 403

    a = Article.query.get_or_404(article_id)
    return jsonify({
        'id': a.id,
        'title': a.title,
        'content': a.content,
        'category': a.category,
        'priority': int(a.priority or 0),
        'is_published': bool(a.is_published),
        'created_at': a.created_at.isoformat() if a.created_at else None
    }), 200
@admin_bp.route('/api/article/<int:article_id>/update', methods=['POST'])
def update_article(article_id):
    user = get_current_user()
    if not can_access_panel(user):
        return jsonify({'error': 'Access denied'}), 403

    a = Article.query.get_or_404(article_id)

    data = request.get_json() or {}

    title = (data.get('title') or '').strip()
    content = data.get('content') or ''
    category = (data.get('category') or '').strip()

    if not title or not content or not category:
        return jsonify({'error': 'Thiếu dữ liệu'}), 400

    a.title = title
    a.content = content
    a.category = category
    a.priority = int(data.get('priority', 0))
    a.is_published = bool(data.get('is_published', True))

    db.session.commit()
    return jsonify({'success': True}), 200    

@admin_bp.route('/api/article/<int:article_id>/delete', methods=['POST'])
def delete_article(article_id):
    user = get_current_user()
    if not can_access_panel(user):
        return jsonify({'error': 'Access denied'}), 403

    db.session.delete(Article.query.get_or_404(article_id))
    db.session.commit()
    return jsonify({'success': True}), 200

@admin_bp.route('/api/admin/set-role', methods=['POST'])
def set_role():
    admin = get_current_user()
    if not is_admin_only(admin):
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    role = (data.get('role') or '').strip()

    if not username or role not in ('user', 'staff', 'admin'):
        return jsonify({'error': 'Thiếu username hoặc role không hợp lệ'}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'Không tìm thấy user'}), 404

    if role == 'user':
        user.is_staff = False
        user.is_admin = False
    elif role == 'staff':
        user.is_staff = True
        user.is_admin = False
    elif role == 'admin':
        user.is_staff = True
        user.is_admin = True

    db.session.commit()
    return jsonify({
        'success': True,
        'username': user.username,
        'is_staff': user.is_staff,
        'is_admin': user.is_admin
    }), 200
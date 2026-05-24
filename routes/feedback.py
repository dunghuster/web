import html
from flask import Blueprint, render_template, request, jsonify, abort
from sqlalchemy.orm import joinedload
from extensions import db
from models import FeedbackPost, FeedbackComment, User
from utils import get_current_user, is_staff_user

feedback_bp = Blueprint('feedback', __name__)

def feedback_can_view(post: FeedbackPost, user: User):
    if post.status == 'approved':
        return True
    return bool(user and (is_staff_user(user) or post.user_id == user.id))

@feedback_bp.route('/feedback', methods=['GET', 'POST'])
def feedback_page():
    user = get_current_user()

    if request.method == 'POST':
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401

        data = request.get_json() or {}
        title = (data.get('title') or '').strip()
        content = (data.get('content') or '').strip()
        category = (data.get('category') or 'suggestion').strip()

        if not title or not content:
            return jsonify({'error': 'Thiếu tiêu đề hoặc nội dung'}), 400

        post = FeedbackPost(
            user_id=user.id,
            title=title,
            content=content,
            category=category,
            status='pending'
        )
        db.session.add(post)
        db.session.commit()
        return jsonify({'success': True, 'id': post.id}), 200

    # Phân trang: 10 bài / trang + chống lag bằng joinedload
    page = request.args.get('page', 1, type=int)
    q = FeedbackPost.query.options(joinedload(FeedbackPost.user)).order_by(FeedbackPost.created_at.desc())
    
    if not user or not is_staff_user(user):
        q = q.filter(FeedbackPost.status == 'approved')
        
    pagination = q.paginate(page=page, per_page=10, error_out=False)

    return render_template('feedback.html', posts=pagination.items, pagination=pagination, current_user=user)

@feedback_bp.route('/feedback/<int:post_id>')
def feedback_detail(post_id):
    user = get_current_user()
    post = FeedbackPost.query.get_or_404(post_id)
    if not feedback_can_view(post, user):
        abort(404)
    return render_template('feedback_detail.html', post=post, current_user=user)

@feedback_bp.route('/api/feedback/list')
def api_feedback_list():
    user = get_current_user()

    page = request.args.get('page', 1, type=int)
    q = FeedbackPost.query.options(joinedload(FeedbackPost.user)).order_by(FeedbackPost.created_at.desc())
    
    if not user or not is_staff_user(user):
        q = q.filter(FeedbackPost.status == 'approved')

    pagination = q.paginate(page=page, per_page=10, error_out=False)

    posts = []
    for p in pagination.items:
        posts.append({
            'id': p.id,
            'title': p.title,
            'category': p.category,
            'status': p.status,
            'author': p.user.username,
            'created_at': p.created_at.strftime('%d/%m %H:%M')
        })
    return jsonify({
        'posts': posts,
        'has_next': pagination.has_next,
        'current_page': pagination.page,
        'is_staff': bool(user and is_staff_user(user))
    }), 200

@feedback_bp.route('/api/feedback/<int:post_id>')
def api_feedback_post(post_id):
    user = get_current_user()
    post = FeedbackPost.query.get_or_404(post_id)
    if not feedback_can_view(post, user):
        return jsonify({'error': 'Not found'}), 404

    comments = FeedbackComment.query.filter_by(post_id=post.id)\
        .options(joinedload(FeedbackComment.user))\
        .order_by(FeedbackComment.created_at.asc()).all()
        
    return jsonify({
        'post': {
            'id': post.id,
            'title': post.title,
            'content': post.content,
            'category': post.category,
            'status': post.status,
            'author': post.user.username,
            'created_at': post.created_at.strftime('%d/%m/%Y %H:%M'),
            'is_owner': bool(user and user.id == post.user_id),
            'can_moderate': bool(user and is_staff_user(user))
        },
        'comments': [{
            'id': c.id,
            'parent_id': c.parent_id,
            'content': html.escape(c.content).replace('\n', '<br>'),
            'author': c.user.username,
            'is_me': bool(user and c.user_id == user.id),
            'is_admin': bool(getattr(c.user, 'is_admin', False)),
            'time': c.created_at.strftime('%H:%M %d/%m')
        } for c in comments]
    }), 200

@feedback_bp.route('/api/feedback/<int:post_id>/comment', methods=['POST'])
def api_feedback_comment(post_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    post = FeedbackPost.query.get_or_404(post_id)
    if not feedback_can_view(post, user):
        return jsonify({'error': 'Not allowed'}), 403

    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    parent_id = data.get('parent_id')

    if not content:
        return jsonify({'error': 'Nội dung trống'}), 400

    if parent_id:
        parent = FeedbackComment.query.get(parent_id)
        if not parent or parent.post_id != post.id:
            return jsonify({'error': 'Parent comment không hợp lệ'}), 400

    c = FeedbackComment(post_id=post.id, user_id=user.id, parent_id=parent_id, content=content)
    db.session.add(c)
    db.session.commit()
    return jsonify({'success': True, 'id': c.id}), 200

@feedback_bp.route('/api/feedback/<int:post_id>/edit', methods=['POST'])
def api_feedback_edit(post_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    post = FeedbackPost.query.get_or_404(post_id)
    if post.user_id != user.id and not is_staff_user(user):
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    category = (data.get('category') or post.category).strip()

    if not title or not content:
        return jsonify({'error': 'Thiếu tiêu đề hoặc nội dung'}), 400

    post.title = title
    post.content = content
    post.category = category

    if post.user_id == user.id and not is_staff_user(user):
        post.status = 'pending'

    db.session.commit()
    return jsonify({'success': True}), 200

@feedback_bp.route('/api/feedback/<int:post_id>/delete', methods=['POST'])
def api_feedback_delete(post_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    post = FeedbackPost.query.get_or_404(post_id)
    if post.user_id != user.id and not is_staff_user(user):
        return jsonify({'error': 'Forbidden'}), 403

    db.session.delete(post)
    db.session.commit()
    return jsonify({'success': True}), 200

@feedback_bp.route('/api/admin/feedback/<int:post_id>/status', methods=['POST'])
def api_admin_feedback_status(post_id):
    user = get_current_user()
    if not user or not is_staff_user(user):
        return jsonify({'error': 'Forbidden'}), 403

    post = FeedbackPost.query.get_or_404(post_id)
    data = request.get_json() or {}
    status = (data.get('status') or '').strip()

    if status not in ['approved', 'hidden', 'pending']:
        return jsonify({'error': 'Status không hợp lệ'}), 400

    post.status = status
    db.session.commit()
    return jsonify({'success': True}), 200
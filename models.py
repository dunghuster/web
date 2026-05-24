from extensions import db
from datetime import datetime, timezone, timedelta

# ==================== HÀM LẤY GIỜ VIỆT NAM ====================
def get_vn_time():
    return datetime.now(timezone(timedelta(hours=7)))

# ==================== MODELS ====================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_staff = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_vn_time)

    # Số dư web (đơn vị: VND). Sau này user dùng số dư này để đổi/nạp vào server.
    balance = db.Column(db.Integer, default=0, nullable=False)

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref='articles')
    created_at = db.Column(db.DateTime, default=get_vn_time)
    is_published = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=0)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), default='support')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='tickets')
    status = db.Column(db.String(20), default='open')
    created_at = db.Column(db.DateTime, default=get_vn_time)
    messages = db.relationship(
        'TicketMessage',
        backref='ticket',
        cascade="all, delete-orphan",
        order_by="TicketMessage.created_at.asc()"
    )

class TicketMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender = db.relationship('User')
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=get_vn_time)

class FeedbackPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='suggestion')
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=get_vn_time)
    updated_at = db.Column(db.DateTime, default=get_vn_time, onupdate=get_vn_time)
    user = db.relationship('User', backref=db.backref('feedback_posts', lazy=True))

class FeedbackComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('feedback_post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('feedback_comment.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=get_vn_time)
    post = db.relationship('FeedbackPost', backref=db.backref('comments', lazy=True, cascade="all,delete-orphan"))
    user = db.relationship('User', backref=db.backref('feedback_comments', lazy=True))
    parent = db.relationship('FeedbackComment', remote_side=[id], backref=db.backref('replies', lazy=True, cascade="all,delete-orphan"))

class Topup(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Mã nội dung chuyển khoản (unique)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # User tạo yêu cầu nạp
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('topups', lazy=True))

    # Số tiền yêu cầu nạp (VND)
    amount = db.Column(db.Integer, nullable=False)

    # pending / paid
    status = db.Column(db.String(20), default='pending', nullable=False)

    # chống trùng theo referenceCode
    sepay_reference = db.Column(db.String(128), unique=True, nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=get_vn_time)
    paid_at = db.Column(db.DateTime, nullable=True)

    # Lưu payload để đối soát
    raw_payload = db.Column(db.Text, nullable=True)
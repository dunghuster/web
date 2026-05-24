import os
import requests
import hmac
import hashlib
import json
import time
import re
import secrets
import string
from dotenv import load_dotenv

from flask import Flask, render_template, jsonify, session, Response, request
from werkzeug.security import generate_password_hash

# ==================== IMPORT TỪ CÁC FILE ĐÃ TÁCH ====================
from extensions import db
from models import User, Article, Topup, get_vn_time
from utils import get_current_user

load_dotenv()

app = Flask(__name__)

# ==================== CẤU HÌNH DATABASE & APP ====================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(INSTANCE_DIR, 'wiki.db')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback-secret-key')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Khởi tạo db gắn với app
db.init_app(app)

# ==================== ĐĂNG KÝ BLUEPRINTS ====================
from routes.auth import auth_bp
from routes.ticket import ticket_bp
from routes.feedback import feedback_bp
from routes.admin import admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(ticket_bp)
app.register_blueprint(feedback_bp)
app.register_blueprint(admin_bp)

IA_PACK_URL = "http://216.163.186.32:12000/generated.zip"
MC_HOST = os.getenv('MC_HOST', 'play.genzera.online')

# ==================== HELPERS ====================
def generate_topup_code(length=8):
    alphabet = string.ascii_uppercase + string.digits
    return "GZ" + "".join(secrets.choice(alphabet) for _ in range(length))

def verify_sepay_signature(secret: str, timestamp: str, raw_body: bytes, signature_header: str) -> bool:
    """
    Observed headers:
      - X-Sepay-Timestamp: <unix>
      - X-Sepay-Signature: sha256=<hex>

    Assumption:
      signature = HMAC_SHA256(secret, f"{timestamp}.{raw_body}")
    """
    if not secret or not timestamp or not signature_header:
        return False

    given = signature_header.strip()
    if given.startswith("sha256="):
        given = given.split("=", 1)[1].strip()

    msg = timestamp.encode("utf-8") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given)

# ==================== CONTEXT PROCESSOR ====================
@app.context_processor
def inject_global_data():
    def get_user(user_id):
        return User.query.get(user_id) if user_id else None
    return dict(get_user=get_user)

# ==================== PUBLIC ROUTES ====================
@app.route('/api/me')
def api_me():
    user = get_current_user()
    if not user:
        return jsonify({'logged_in': False}), 200
    return jsonify({
        'logged_in': True,
        'username': user.username,
        'is_admin': bool(user.is_admin),
        'is_staff': bool(user.is_staff),
        'can_access_panel': bool(user.is_admin or user.is_staff)
    }), 200

@app.route('/')
def index():
    articles_by_category = {
        cat: Article.query.filter_by(category=cat, is_published=True)
        .order_by(Article.priority.desc(), Article.created_at.desc())
        .all()
        for cat in ['event', 'maintenance', 'news', 'recharge', 'support']
    }
    return render_template('index.html', articles=articles_by_category)

@app.route('/article/<int:article_id>')
def view_article(article_id):
    return render_template('article.html', article=Article.query.get_or_404(article_id))

@app.route('/download-pack')
def download_pack():
    try:
        req = requests.get(IA_PACK_URL, stream=True, timeout=10)
        req.raise_for_status()

        return Response(
            req.iter_content(chunk_size=8192),
            headers={
                "Content-Type": "application/zip",
                "Content-Disposition": 'attachment; filename="GenZEra_ItemsAdder_Pack.zip"'
            }
        )
    except Exception as e:
        return f"Không tải được pack. Hãy thử lại sau. Lỗi: {str(e)}", 500

@app.route('/category/<string:cat>')
def view_category(cat):
    allowed = ['event', 'maintenance', 'news', 'recharge', 'support']
    if cat not in allowed:
        return "Not Found", 404

    articles = (Article.query
                .filter_by(category=cat, is_published=True)
                .order_by(Article.priority.desc(), Article.created_at.desc())
                .all())

    category_names = {
        'event': 'Sự Kiện',
        'maintenance': 'Bảo Trì',
        'news': 'Thông Báo',
        'recharge': 'Nạp Thẻ',
        'support': 'Hỗ Trợ'
    }

    return render_template(
        'category.html',
        category=cat,
        category_title=category_names.get(cat, cat),
        articles=articles
    )

# ==================== RECHARGE ROUTES (VietQR) ====================
@app.route('/recharge')
def recharge_page():
    user = get_current_user()
    if not user:
        return "Bạn cần đăng nhập để nạp.", 401
    return render_template('recharge.html')

@app.route('/api/recharge/vietqr', methods=['POST'])
def api_recharge_vietqr():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Bạn cần đăng nhập'}), 401

    data = request.get_json() or {}
    amount = int(data.get('amount') or 0)
    if amount < 1000:
        return jsonify({'error': 'Số tiền không hợp lệ (>= 1000)'}), 400

    # tạo Topup pending với code unique
    for _ in range(10):
        code = generate_topup_code(8)
        if not Topup.query.filter_by(code=code).first():
            break
    else:
        return jsonify({'error': 'Không tạo được mã nạp, thử lại'}), 500

    topup = Topup(code=code, user_id=user.id, amount=amount, status='pending')
    db.session.add(topup)
    db.session.commit()

    bank_code = os.getenv("VQR_BANK_CODE", "MB")
    account_no = os.getenv("VQR_ACCOUNT_NO", "0337164076")
    account_name = os.getenv("VQR_ACCOUNT_NAME", "NGUYEN QUANG DUNG")

    qr_url = (
        f"https://img.vietqr.io/image/{bank_code}-{account_no}-compact2.png"
        f"?amount={amount}&addInfo={code}&accountName={account_name.replace(' ', '%20')}"
    )

    return jsonify({
        'success': True,
        'amount': amount,
        'code': code,
        'qr_url': qr_url
    }), 200

# ==================== SEPAY WEBHOOK ====================
@app.route('/webhook/sepay', methods=['POST'])
def webhook_sepay():
    secret = os.getenv("SEPAY_WEBHOOK_SECRET", "")
    timestamp = request.headers.get("X-Sepay-Timestamp", "")
    sig = request.headers.get("X-Sepay-Signature", "")

    raw = request.get_data()

    # chống replay (10 phút)
    try:
        ts = int(timestamp)
        if abs(int(time.time()) - ts) > 600:
            print("[SEPAY DROP] invalid timestamp:", timestamp)
            return "invalid timestamp", 400
    except Exception:
        print("[SEPAY DROP] invalid timestamp (parse fail):", timestamp)
        return "invalid timestamp", 400

    if not verify_sepay_signature(secret, timestamp, raw, sig):
        print("[SEPAY DROP] invalid signature", {"timestamp": timestamp, "sig": sig})
        return "invalid signature", 401

    payload = request.get_json(silent=True) or {}

    # LOG để bạn thấy webhook có tới hay không (dù không match code)
    print("[SEPAY HIT]", json.dumps(payload, ensure_ascii=False))

    if payload.get("transferType") != "in":
        print("[SEPAY IGNORE] transferType:", payload.get("transferType"))
        return "ok", 200

    amount = int(payload.get("transferAmount") or 0)
    content = (payload.get("content") or "").strip()
    description = (payload.get("description") or "").strip()
    reference = (payload.get("referenceCode") or payload.get("code") or "").strip()

    # tìm code topup trong content + description (thực tế nhiều bank nằm ở description)
    text = f"{content} {description}".upper()
    m = re.search(r"\b(GZ[A-Z0-9]{6,32})\b", text)

    if not m:
        print("[SEPAY NO CODE]", {"content": content, "description": description, "amount": amount, "reference": reference})
        return "no topup code", 200

    code = m.group(1)
    topup = Topup.query.filter_by(code=code).first()
    if not topup:
        print("[SEPAY TOPUP NOT FOUND]", {"code": code, "amount": amount, "reference": reference})
        return "topup not found", 200

    # idempotent
    if topup.status == "paid":
        print("[SEPAY ALREADY PAID]", {"code": code, "topup_id": topup.id})
        return "ok", 200

    # chống trùng reference
    if reference:
        exists_ref = Topup.query.filter(Topup.sepay_reference == reference, Topup.id != topup.id).first()
        if exists_ref:
            print("[SEPAY DUP REF]", {"reference": reference, "code": code, "topup_id": topup.id})
            return "duplicate reference", 200

    if amount < int(topup.amount):
        print("[SEPAY AMOUNT NOT ENOUGH]", {"code": code, "need": topup.amount, "got": amount})
        return "amount not enough", 200

    # mark paid + cộng số dư web
    topup.status = "paid"
    topup.paid_at = get_vn_time()
    topup.sepay_reference = reference or None
    topup.raw_payload = json.dumps(payload, ensure_ascii=False)

    topup.user.balance = int(topup.user.balance or 0) + int(topup.amount)
    db.session.commit()

    print("[TOPUP PAID]", code, "amount=", topup.amount, "user_id=", topup.user_id, "new_balance=", topup.user.balance)
    return "ok", 200

# ==================== OTHER API ====================
@app.route('/api/mc-status')
def api_mc_status():
    from mcstatus import JavaServer
    try:
        server = JavaServer.lookup(MC_HOST, timeout=2)
        status = server.status()
        return jsonify({'online': True, 'players': f"{status.players.online}/{status.players.max}"})
    except Exception:
        return jsonify({'online': False, 'players': "Bảo trì"})

# ==================== INIT DATABASE ====================
with app.app_context():
    db.create_all()

    if not User.query.filter_by(username='admin').first():
        default_pass = os.getenv('DEFAULT_ADMIN_PASS', 'admin123')
        db.session.add(User(
            username='admin',
            email='admin@genz.com',
            password=generate_password_hash(default_pass),
            is_admin=True,
            is_staff=True
        ))
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
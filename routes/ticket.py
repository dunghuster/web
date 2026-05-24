import html
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from sqlalchemy.orm import joinedload
from extensions import db
from models import Ticket, TicketMessage, User

ticket_bp = Blueprint('ticket', __name__)

@ticket_bp.route('/tickets', methods=['GET', 'POST'])
def tickets():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        data = request.get_json() or {}
        title = (data.get('title') or '').strip()
        category = (data.get('category') or 'support').strip()
        message = data.get('message') or ''

        if not title or not message:
            return jsonify({'error': 'Thiếu dữ liệu'}), 400

        ticket = Ticket(title=title, category=category, user_id=user.id)
        db.session.add(ticket)
        db.session.commit()

        db.session.add(TicketMessage(ticket_id=ticket.id, sender_id=user.id, message=message))
        db.session.commit()
        return jsonify({'success': True}), 200

    # Render giao diện HTML ban đầu (JavaScript sẽ tự động lo việc gọi API load dữ liệu)
    return render_template('tickets.html', is_admin=user.is_admin)

@ticket_bp.route('/ticket/<int:ticket_id>', methods=['GET', 'POST'])
def ticket_detail(ticket_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])
    ticket = Ticket.query.get_or_404(ticket_id)
    if not user.is_admin and ticket.user_id != user.id:
        return "Cấm", 403

    if request.method == 'POST':
        data = request.get_json() or {}
        if data.get('action') == 'close' and user.is_admin:
            ticket.status = 'closed'
        elif data.get('action') == 'delete' and user.is_admin:
            db.session.delete(ticket)
            db.session.commit()
            return jsonify({'success': True, 'deleted': True}), 200
        else:
            if ticket.status == 'closed':
                return jsonify({'error': 'Ticket đã đóng'}), 400

            msg = data.get('message') or ''
            if msg.strip():
                db.session.add(TicketMessage(ticket_id=ticket.id, sender_id=user.id, message=msg))
                ticket.status = 'answered' if user.is_admin else 'open'
        db.session.commit()
        return jsonify({'success': True}), 200

    return render_template('ticket_detail.html', ticket=ticket, current_user=user)

@ticket_bp.route('/api/ticket/<int:ticket_id>/messages')
def api_ticket_messages(ticket_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user = User.query.get(session['user_id'])
    
    # Dùng joinedload lấy sẵn thông tin sender để không bị N+1 query
    ticket = Ticket.query.options(joinedload(Ticket.messages).joinedload(TicketMessage.sender)).get_or_404(ticket_id)
    
    if not user.is_admin and ticket.user_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403

    msgs = []
    for m in ticket.messages:
        msgs.append({
            'sender_name': m.sender.username,
            'is_me': m.sender_id == user.id,
            'is_admin': m.sender.is_admin,
            'time': m.created_at.strftime('%H:%M %d/%m'),
            'message': html.escape(m.message).replace('\n', '<br>')
        })
    return jsonify({'messages': msgs, 'status': ticket.status})


# ==================== ĐÂY LÀ API BỊ BỎ QUÊN ====================
@ticket_bp.route('/api/tickets')
def api_tickets():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user = User.query.get(session['user_id'])
    
    # Lấy tham số trang hiện tại từ URL do JS truyền lên (mặc định là trang 1)
    page = request.args.get('page', 1, type=int)

    # Dùng joinedload để gộp query (Chống lag) và paginate để phân trang (10 vé/trang)
    if user.is_admin:
        pagination = Ticket.query.options(joinedload(Ticket.user)).order_by(Ticket.status.desc(), Ticket.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    else:
        pagination = Ticket.query.filter_by(user_id=user.id).options(joinedload(Ticket.user)).order_by(Ticket.created_at.desc()).paginate(page=page, per_page=10, error_out=False)

    tickets = []
    for t in pagination.items:
        tickets.append({
            'id': t.id,
            'title': t.title,
            'category': t.category,
            'status': t.status,
            'created_at': t.created_at.strftime('%d/%m %H:%M'),
            'username': getattr(t.user, 'username', 'Unknown')
        })

    return jsonify({
        'tickets': tickets,
        'has_next': pagination.has_next,
        'current_page': pagination.page,
        'is_admin': bool(user.is_admin)
    }), 200
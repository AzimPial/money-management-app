from flask import Flask, render_template, request, redirect, url_for, session, g
from functools import wraps
import json
import os
import logging
import random
import string
import uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_demo_persistent_2026'
app.config['PERMANENT_SESSION_LIFETIME'] = 31536000  # 1 year
app.config['SESSION_COOKIE_NAME'] = 'synccent_session'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set True for HTTPS production

logging.basicConfig(level=logging.INFO)

import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

# Read credentials from environment variable or local file
creds_json = os.environ.get('FIREBASE_CREDS')
if creds_json:
    cred_dict = json.loads(creds_json)
    cred = credentials.Certificate(cred_dict)
else:
    try:
        cred = credentials.Certificate('firebase-service-account.json')
    except:
        cred = None

if cred:
    firebase_admin.initialize_app(cred)
    db = firestore.client()
else:
    db = None

def get_db():
    return db

def check_db():
    if db is None:
        return "Firebase not configured. Set FIREBASE_CREDS environment variable."
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_user_group_id(username):
    users_ref = db.collection('users').document(username)
    user_doc = users_ref.get()
    if user_doc.exists:
        return user_doc.to_dict().get('group_id')
    return None

@app.route('/register', methods=['GET', 'POST'])
def register():
    db_error = check_db()
    if db_error:
        return render_template('login.html', error=db_error, is_register=True)
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return render_template('login.html', error="Please enter both username and password", is_register=True)

        users_ref = db.collection('users')
        existing = users_ref.document(username).get()

        if existing.exists:
            return render_template('login.html', error="Username already exists", is_register=True)

        users_ref.document(username).set({
            'username': username,
            'password': password
        })
        session['username'] = username
        session.permanent = True
        return redirect(url_for('index'))
    return render_template('login.html', is_register=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return render_template('login.html', error="Please enter both username and password", is_register=False)

        users_ref = db.collection('users').document(username)
        user_doc = users_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            if user_data.get('password') == password:
                session['username'] = username
                session.permanent = True
                return redirect(url_for('index'))
        
        return render_template('login.html', error="Invalid username or password", is_register=False)
    return render_template('login.html', is_register=False)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    group_name = request.form.get('group_name')
    if group_name:
        group_id = str(uuid.uuid4())
        invite_code = generate_invite_code()

        group_data = {
            'id': group_id,
            'name': group_name,
            'invite_code': invite_code
        }
        db.collection('groups').document(group_id).set(group_data)
        
        db.collection('users').document(session['username']).update({
            'group_id': group_id
        })

    return redirect(url_for('index'))

@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    invite_code = request.form.get('invite_code')
    
    groups_ref = db.collection('groups')
    groups = groups_ref.where('invite_code', '==', invite_code.upper()).stream()
    
    group_doc = None
    for g in groups:
        group_doc = g
        break
    
    if group_doc:
        group_id = group_doc.id
        db.collection('users').document(session['username']).update({
            'group_id': group_id
        })
        return redirect(url_for('index'))

    return render_template('group_setup.html', username=session['username'], error="Invalid Invite Code")

@app.route('/')
@login_required
def index():
    username = session['username']
    group_id = get_user_group_id(username)

    if not group_id:
        return render_template('group_setup.html', username=username)

    group_doc = db.collection('groups').document(group_id).get()
    group = group_doc.to_dict() if group_doc.exists else None

    expenses_ref = db.collection('expenses').where('group_id', '==', group_id)
    expenses = [e.to_dict() for e in expenses_ref.stream()]

    expenses_sorted = sorted(expenses, key=lambda x: x.get('created_at', ''), reverse=True)

    total = sum(e.get('amount', 0) for e in expenses)

    return render_template('index.html',
                         expenses=expenses_sorted,
                         total=total,
                         username=username,
                         group_name=group['name'] if group else 'My Group',
                         invite_code=group['invite_code'] if group else 'N/A')

@app.route('/add', methods=['POST'])
@login_required
def add_expense():
    username = session['username']
    user_doc = db.collection('users').document(username).get()
    user_data = user_doc.to_dict()
    group_id = user_data.get('group_id')

    if not group_id:
        return redirect(url_for('index'))

    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')

    if description and amount:
        expense_id = str(uuid.uuid4())
        expense_data = {
            'id': expense_id,
            'group_id': group_id,
            'description': description,
            'amount': float(amount),
            'category': category or 'General',
            'paid_by': username,
            'created_at': datetime.now().isoformat()
        }
        db.collection('expenses').document(expense_id).set(expense_data)
    
    return redirect(url_for('index'))

@app.route('/delete_expense/<expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    username = session['username']
    user_doc = db.collection('users').document(username).get()
    user_data = user_doc.to_dict()
    group_id = user_data.get('group_id')

    if not group_id:
        return redirect(url_for('index'))

    db.collection('expenses').document(expense_id).delete()
    return redirect(url_for('index'))

@app.route('/edit_expense/<expense_id>', methods=['POST'])
@login_required
def edit_expense(expense_id):
    username = session['username']
    user_doc = db.collection('users').document(username).get()
    user_data = user_doc.to_dict()
    group_id = user_data.get('group_id')

    if not group_id:
        return redirect(url_for('index'))

    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')

    expense_ref = db.collection('expenses').document(expense_id)
    expense_doc = expense_ref.get()
    
    if expense_doc.exists:
        update_data = {}
        if description:
            update_data['description'] = description
        if amount:
            update_data['amount'] = float(amount)
        if category:
            update_data['category'] = category
        
        if update_data:
            expense_ref.update(update_data)
    
    return redirect(url_for('index'))

@app.route('/members')
@login_required
def view_members():
    username = session['username']
    user_doc = db.collection('users').document(username).get()
    user_data = user_doc.to_dict()
    group_id = user_data.get('group_id')

    if not group_id:
        return redirect(url_for('index'))

    group_doc = db.collection('groups').document(group_id).get()
    group = group_doc.to_dict() if group_doc.exists else {}

    members_ref = db.collection('users').where('group_id', '==', group_id)
    members = [u.to_dict().get('username') for u in members_ref.stream()]

    return render_template('members.html',
                         members=members,
                         group_name=group.get('name', 'My Group'),
                         username=username,
                         invite_code=group.get('invite_code', 'N/A'))

@app.route('/leave_group', methods=['POST'])
@login_required
def leave_group():
    username = session['username']
    user_doc = db.collection('users').document(username).get()
    user_data = user_doc.to_dict()
    group_id = user_data.get('group_id')

    if not group_id:
        return redirect(url_for('index'))

    db.collection('users').document(username).update({
        'group_id': firestore.DELETE_FIELD
    })

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)
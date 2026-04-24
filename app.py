from flask import Flask, render_template, request, redirect, url_for, session
from functools import wraps
import json
import os
import logging
import random
import string
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_demo'

logging.basicConfig(level=logging.INFO)

DATA_FILE = 'expenses.json'
USERS_FILE = 'users.json'
GROUPS_FILE = 'groups.json'

def load_data(filename):
    try:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                content = f.read()
                if not content:
                    return [] if filename == DATA_FILE else {}
                return json.loads(content)
    except Exception as e:
        app.logger.error(f"Error loading {filename}: {e}")
        return [] if filename == DATA_FILE else {}
    return [] if filename == DATA_FILE else {}

def save_data(filename, data):
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        app.logger.error(f"Error saving {filename}: {e}")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        users = load_data(USERS_FILE)
        
        if username in users and check_password_hash(users[username]['password'], password):
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')
    users = load_data(USERS_FILE)
    
    if username in users:
        return render_template('login.html', error="Username already exists")
    
    users[username] = {'password': generate_password_hash(password), 'group_id': None}
    save_data(USERS_FILE, users)
    session['username'] = username
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    group_name = request.form.get('group_name')
    if group_name:
        groups = load_data(GROUPS_FILE)
        group_id = str(uuid.uuid4())
        invite_code = generate_invite_code()
        
        groups[group_id] = {
            'name': group_name,
            'invite_code': invite_code,
            'members': [session['username']]
        }
        save_data(GROUPS_FILE, groups)
        
        users = load_data(USERS_FILE)
        users[session['username']]['group_id'] = group_id
        save_data(USERS_FILE, users)
        
    return redirect(url_for('index'))

@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    invite_code = request.form.get('invite_code')
    groups = load_data(GROUPS_FILE)
    
    for gid, gdata in groups.items():
        if gdata['invite_code'] == invite_code.upper():
            users = load_data(USERS_FILE)
            users[session['username']]['group_id'] = gid
            save_data(USERS_FILE, users)
            
            # Add to group members if not already there
            if session['username'] not in gdata['members']:
                gdata['members'].append(session['username'])
                save_data(GROUPS_FILE, groups)
                
            return redirect(url_for('index'))
            
    return render_template('group_setup.html', username=session['username'], error="Invalid Invite Code")

@app.route('/')
@login_required
def index():
    users = load_data(USERS_FILE)
    username = session['username']
    group_id = users.get(username, {}).get('group_id')
    
    if not group_id:
        return render_template('group_setup.html', username=username)
        
    groups = load_data(GROUPS_FILE)
    group_data = groups.get(group_id, {})
    
    all_expenses = load_data(DATA_FILE)
    # Filter expenses by group_id
    group_expenses = [e for e in all_expenses if e.get('group_id') == group_id]
    
    total = 0
    for e in group_expenses:
        try:
            total += float(e.get('amount', 0))
        except (ValueError, TypeError):
            continue
            
    return render_template('index.html', 
                           expenses=group_expenses, 
                           total=total, 
                           username=username,
                           group_name=group_data.get('name', 'My Group'),
                           invite_code=group_data.get('invite_code', 'N/A'))

@app.route('/add', methods=['POST'])
@login_required
def add_expense():
    users = load_data(USERS_FILE)
    group_id = users.get(session['username'], {}).get('group_id')
    
    if not group_id:
        return redirect(url_for('index'))
        
    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    
    if description and amount:
        expenses = load_data(DATA_FILE)
        expenses.append({
            'group_id': group_id,
            'description': description,
            'amount': amount,
            'category': category or 'General',
            'paid_by': session['username']
        })
        save_data(DATA_FILE, expenses)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)

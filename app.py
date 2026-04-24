from flask import Flask, render_template, request, redirect, url_for, session
from functools import wraps
import json
import os
import logging
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_demo' # Required for sessions

# Set up logging to catch errors
logging.basicConfig(level=logging.INFO)

DATA_FILE = 'expenses.json'
USERS_FILE = 'users.json'

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

# Decorator to require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
    
    users[username] = {'password': generate_password_hash(password)}
    save_data(USERS_FILE, users)
    session['username'] = username
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    try:
        expenses = load_data(DATA_FILE)
        total = 0
        for e in expenses:
            try:
                total += float(e.get('amount', 0))
            except (ValueError, TypeError):
                continue
        return render_template('index.html', expenses=expenses, total=total, username=session['username'])
    except Exception as e:
        app.logger.error(f"Index page error: {e}")
        return "Internal Server Error", 500

@app.route('/add', methods=['POST'])
@login_required
def add_expense():
    try:
        description = request.form.get('description')
        amount = request.form.get('amount')
        category = request.form.get('category')
        
        if description and amount:
            expenses = load_data(DATA_FILE)
            expenses.append({
                'description': description,
                'amount': amount,
                'category': category or 'General',
                'paid_by': session['username']
            })
            save_data(DATA_FILE, expenses)
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"Add expense error: {e}")
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)

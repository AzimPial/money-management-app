from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from functools import wraps
import os
import logging
import random
import string
import uuid
from datetime import datetime, timedelta
from calendar import monthrange

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_demo_persistent_2026'
app.config['PERMANENT_SESSION_LIFETIME'] = 31536000
app.config['SESSION_COOKIE_NAME'] = 'synccent_session'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

logging.basicConfig(level=logging.INFO)

DEFAULT_CATEGORIES = [
    'Food', 'Transport', 'Rent', 'Shopping', 'Entertainment',
    'Utilities', 'Healthcare', 'Trip', 'Others'
]

import firebase_admin
from firebase_admin import credentials, firestore

db = None
creds = None

# Method 1: Try individual env vars
project_id = os.environ.get('FIREBASE_PROJECT_ID')
private_key = os.environ.get('FIREBASE_PRIVATE_KEY')
client_email = os.environ.get('FIREBASE_CLIENT_EMAIL')

if project_id and private_key and client_email:
    try:
        creds_dict = {
            "type": "service_account",
            "project_id": project_id,
            "private_key": private_key.replace('\\n', '\n'),
            "client_email": client_email
        }
        creds = credentials.Certificate(creds_dict)
    except Exception as e:
        logging.error(f"Method 1 failed: {e}")

# Method 2: Try from embedded Python config
if not creds:
    try:
        from firebase_config import get_firebase_creds
        creds = credentials.Certificate(get_firebase_creds())
    except Exception as e:
        logging.error(f"Method 2 failed: {e}")

if creds:
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(creds)
        db = firestore.client()
    except Exception as e:
        logging.error(f"Firebase init error: {e}")

def get_db():
    return db

def check_db():
    if db is None:
        return "Database not configured"
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

def get_current_period():
    now = datetime.now()
    year = now.year
    month = now.month
    month_name = now.strftime('%B %Y')
    return {
        'id': f'{year}-{month:02d}',
        'type': 'month',
        'name': month_name,
        'start': datetime(year, month, 1).isoformat(),
        'end': datetime(year, month, monthrange(year, month)[1]).isoformat()
    }

def get_period_totals(expenses):
    category_totals = {}
    for e in expenses:
        cat = e.get('category', 'Others')
        category_totals[cat] = category_totals.get(cat, 0) + e.get('amount', 0)
    return category_totals

def get_group_categories(group_id):
    if not db:
        return DEFAULT_CATEGORIES
    try:
        group_doc = db.collection('groups').document(group_id).get()
        if group_doc.exists:
            custom_cats = group_doc.to_dict().get('custom_categories', [])
            if custom_cats:
                return DEFAULT_CATEGORIES + custom_cats
    except:
        pass
    return DEFAULT_CATEGORIES

def get_user_group_id(username):
    if not db:
        return None
    try:
        user_doc = db.collection('users').document(username).get()
        if user_doc.exists:
            return user_doc.to_dict().get('group_id')
    except Exception as e:
        logging.error(f"get_user_group_id error: {e}")
    return None

def get_user_groups(username):
    if not db:
        return []
    try:
        user_doc = db.collection('users').document(username).get()
        if user_doc.exists:
            return user_doc.to_dict().get('groups', [])
    except Exception as e:
        logging.error(f"get_user_groups error: {e}")
    return []

def get_personal_categories(username):
    if not db:
        return DEFAULT_CATEGORIES
    try:
        user_doc = db.collection('users').document(username).get()
        if user_doc.exists:
            custom_cats = user_doc.to_dict().get('custom_categories', [])
            if custom_cats:
                return DEFAULT_CATEGORIES + custom_cats
    except:
        pass
    return DEFAULT_CATEGORIES

def filter_expenses_by_period(expenses, period_id):
    if period_id == 'all':
        return sorted(expenses, key=lambda x: x.get('created_at', ''), reverse=True)
    
    period_parts = period_id.split('-')
    if len(period_parts) == 2:
        year, month = int(period_parts[0]), int(period_parts[1])
        start = datetime(year, month, 1)
        end = datetime(year, month, monthrange(year, month)[1], 23, 59, 59)
        filtered = [
            e for e in expenses
            if e.get('created_at') and start.isoformat() <= e['created_at'] <= end.isoformat()
        ]
        return sorted(filtered, key=lambda x: x.get('created_at', ''), reverse=True)
    
    return sorted(expenses, key=lambda x: x.get('created_at', ''), reverse=True)

def process_expense_data(expenses):
    total = sum(e.get('amount', 0) for e in expenses)
    category_totals = get_period_totals(expenses)
    member_totals = {}
    for e in expenses:
        p = e.get('paid_by', 'Unknown')
        member_totals[p] = member_totals.get(p, 0) + e.get('amount', 0)
    return {
        'total': total,
        'category_totals': category_totals,
        'member_totals': member_totals
    }

def get_periods_options(months=6):
    periods = []
    for i in range(months):
        d = datetime.now() - timedelta(days=i*30)
        periods.append({
            'id': f'{d.year}-{d.month:02d}',
            'name': d.strftime('%B %Y')
        })
    periods.append({'id': 'all', 'name': 'All Time'})
    return periods

def get_user_budget(username, period_id):
    if not db or period_id == 'all':
        return None
    try:
        budget_doc = db.collection('budgets').document(f'{username}_{period_id}').get()
        if budget_doc.exists:
            return budget_doc.to_dict()
    except Exception as e:
        logging.error(f"Get user budget error: {e}")
    return None

def get_group_budget(group_id, period_id):
    if not db or period_id == 'all':
        return None
    try:
        budget_doc = db.collection('budgets').document(f'group_{group_id}_{period_id}').get()
        if budget_doc.exists:
            return budget_doc.to_dict()
    except Exception as e:
        logging.error(f"Get group budget error: {e}")
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

        try:
            existing = db.collection('users').document(username).get()
            if existing.exists:
                return render_template('login.html', error="Username already exists", is_register=True)

            db.collection('users').document(username).set({
                'username': username,
                'password': password
            })
            session['username'] = username
            session.permanent = True
            return redirect(url_for('index'))
        except Exception as e:
            logging.error(f"Register error: {e}")
            return render_template('login.html', error="Registration failed", is_register=True)
    
    return render_template('login.html', is_register=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    db_error = check_db()
    if db_error:
        return render_template('login.html', error=db_error, is_register=False)
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return render_template('login.html', error="Please enter both username and password", is_register=False)

        try:
            user_doc = db.collection('users').document(username).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                if user_data.get('password') == password:
                    session['username'] = username
                    session.permanent = True
                    return redirect(url_for('home'))
            
            return render_template('login.html', error="Invalid username or password", is_register=False)
        except Exception as e:
            logging.error(f"Login error: {e}")
            return render_template('login.html', error="Login failed", is_register=False)
    
    return render_template('login.html', is_register=False)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    username = session['username']
    group_id = get_user_group_id(username)
    groups = get_user_groups(username)

    return render_template('home.html',
                         username=username,
                         has_group=group_id is not None,
                         groups=groups)

@app.route('/groups')
@login_required
def groups_page():
    username = session['username']
    group_id = get_user_group_id(username)

    current_group = None
    if group_id:
        try:
            group_doc = db.collection('groups').document(group_id).get()
            if group_doc.exists:
                current_group = group_doc.to_dict()
                current_group['id'] = group_id
        except:
            pass

    return render_template('groups.html',
                         username=username,
                         current_group=current_group,
                         my_groups=[])

@app.route('/create_new_group', methods=['GET', 'POST'])
@login_required
def create_new_group():
    db_error = check_db()
    if db_error:
        return render_template('home.html', error=db_error)

    username = session['username']

    if request.method == 'POST':
        group_name = request.form.get('group_name', '').strip()
        if group_name:
            group_id = str(uuid.uuid4())
            invite_code = generate_invite_code()
            try:
                db.collection('groups').document(group_id).set({
                    'id': group_id,
                    'name': group_name,
                    'invite_code': invite_code,
                    'created_by': username,
                    'created_at': datetime.now().isoformat()
                })
                db.collection('users').document(username).update({
                    'group_id': group_id
                })
                return redirect(url_for('groups_page'))
            except Exception as e:
                logging.error(f"Create group error: {e}")

    return render_template('create_group.html', username=username)

@app.route('/join_group_page')
@login_required
def join_group_page():
    return render_template('join_group.html')

@app.route('/personal')
@login_required
def personal():
    db_error = check_db()
    if db_error:
        return render_template('personal.html', error=db_error, username=session['username'])
    
    username = session['username']
    current_period = get_current_period()
    period_id = request.args.get('period', current_period['id'])

    try:
        expenses_ref = db.collection('expenses').where('user_id', '==', username)
        all_expenses = [e.to_dict() for e in expenses_ref.stream()]

        expenses_sorted = filter_expenses_by_period(all_expenses, period_id)
        processed = process_expense_data(expenses_sorted)
        categories = get_personal_categories(username)
        periods = get_periods_options()

        budget = get_user_budget(username, period_id)

        return render_template('personal.html',
                         expenses=expenses_sorted,
                         total=processed['total'],
                         category_totals=processed['category_totals'],
                         categories=categories,
                         current_period=period_id,
                         periods=periods,
                         budget=budget,
                         username=username)
    except Exception as e:
        logging.error(f"Personal error: {e}")
        return redirect(url_for('home'))

@app.route('/add_personal', methods=['POST'])
@login_required
def add_personal():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    username = session['username']
    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    expense_date = request.form.get('expense_date')

    if description and amount:
        expense_id = str(uuid.uuid4())
        try:
            created_at = expense_date + 'T00:00:00' if expense_date else datetime.now().isoformat()
            db.collection('expenses').document(expense_id).set({
                'id': expense_id,
                'user_id': username,
                'description': description,
                'amount': float(amount),
                'category': category if category else 'Others',
                'paid_by': username,
                'created_at': created_at
            })
        except Exception as e:
            logging.error(f"Add personal expense error: {e}")

    return redirect(url_for('personal'))

@app.route('/add_personal_category', methods=['POST'])
@login_required
def add_personal_category():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    username = session['username']
    new_category = request.form.get('new_category', '').strip()

    if new_category:
        try:
            user_ref = db.collection('users').document(username)
            user_doc = user_ref.get()
            if user_doc.exists:
                custom_cats = user_doc.to_dict().get('custom_categories', [])
                if new_category not in custom_cats:
                    custom_cats.append(new_category)
                    user_ref.update({'custom_categories': custom_cats})
        except Exception as e:
            logging.error(f"Add personal category error: {e}")

    return redirect(url_for('personal'))

@app.route('/search_personal')
@login_required
def search_personal():
    db_error = check_db()
    if db_error:
        return render_template('personal.html', error=db_error, username=session['username'])
    
    username = session['username']
    query = request.args.get('q', '').lower()
    current_period = get_current_period()
    period_id = request.args.get('period', current_period['id'])

    try:
        expenses_ref = db.collection('expenses').where('user_id', '==', username)
        all_expenses = [e.to_dict() for e in expenses_ref.stream()]

        expenses_sorted = filter_expenses_by_period(all_expenses, period_id)

        if query:
            expenses_sorted = [e for e in expenses_sorted if query in e.get('description', '').lower() or query in e.get('category', '').lower()]

        processed = process_expense_data(expenses_sorted)
        categories = get_personal_categories(username)
        periods = get_periods_options()
        budget = get_user_budget(username, period_id)

        return render_template('personal.html',
                         expenses=expenses_sorted,
                         total=processed['total'],
                         category_totals=processed['category_totals'],
                         categories=categories,
                         current_period=period_id,
                         periods=periods,
                         search_query=query,
                         budget=budget,
                         username=username)
    except Exception as e:
        logging.error(f"Search personal error: {e}")
        return redirect(url_for('personal'))

@app.route('/delete_personal_expense/<expense_id>', methods=['POST'])
@login_required
def delete_personal_expense(expense_id):
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    try:
        db.collection('expenses').document(expense_id).delete()
    except Exception as e:
        logging.error(f"Delete personal expense error: {e}")

    return redirect(url_for('personal'))

@app.route('/edit_personal_expense/<expense_id>', methods=['POST'])
@login_required
def edit_personal_expense(expense_id):
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    expense_date = request.form.get('expense_date')

    try:
        update_data = {}
        if description:
            update_data['description'] = description
        if amount:
            update_data['amount'] = float(amount)
        if category:
            update_data['category'] = category
        if expense_date:
            update_data['created_at'] = expense_date + 'T00:00:00'

        if update_data:
            db.collection('expenses').document(expense_id).update(update_data)
    except Exception as e:
        logging.error(f"Edit personal expense error: {e}")

    return redirect(url_for('personal'))

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))
    
    group_name = request.form.get('group_name')
    if group_name:
        group_id = str(uuid.uuid4())
        invite_code = generate_invite_code()

        try:
            db.collection('groups').document(group_id).set({
                'id': group_id,
                'name': group_name,
                'invite_code': invite_code
            })
            db.collection('users').document(session['username']).update({
                'group_id': group_id
            })
        except Exception as e:
            logging.error(f"Create group error: {e}")

    return redirect(url_for('index'))

@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))
    
    invite_code = request.form.get('invite_code')
    
    try:
        groups = db.collection('groups').where('invite_code', '==', invite_code.upper()).stream()
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
    except Exception as e:
        logging.error(f"Join group error: {e}")

    return render_template('group_setup.html', username=session['username'], error="Invalid Invite Code")

@app.route('/')
@login_required
def index():
    username = session['username']
    group_id = get_user_group_id(username)

    if not group_id:
        return redirect(url_for('home'))

    try:
        group_doc = db.collection('groups').document(group_id).get()
        group = group_doc.to_dict() if group_doc.exists else None

        members_ref = db.collection('users').where('group_id', '==', group_id)
        members = [u.to_dict().get('username') for u in members_ref.stream()]

        current_period = get_current_period()
        period_id = request.args.get('period', current_period['id'])
        member_filter = request.args.get('member', '')

        expenses_ref = db.collection('expenses').where('group_id', '==', group_id)
        all_expenses = [e.to_dict() for e in expenses_ref.stream()]

        expenses_sorted = filter_expenses_by_period(all_expenses, period_id)

        if member_filter:
            expenses_sorted = [e for e in expenses_sorted if e.get('paid_by') == member_filter]

        processed = process_expense_data(expenses_sorted)
        custom_cats = get_group_categories(group_id)
        periods = get_periods_options()
        budget = get_group_budget(group_id, period_id)

        return render_template('index.html',
                         expenses=expenses_sorted,
                         total=processed['total'],
                         category_totals=processed['category_totals'],
                         categories=custom_cats,
                         current_period=period_id,
                         periods=periods,
                         members=members,
                         member_filter=member_filter,
                         member_totals=processed['member_totals'],
                         budget=budget,
                         username=username,
                         group_name=group['name'] if group else 'My Group',
                         invite_code=group['invite_code'] if group else 'N/A')
    except Exception as e:
        logging.error(f"Index error: {e}")
        return redirect(url_for('home'))

@app.route('/add', methods=['POST'])
@login_required
def add_expense():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    username = session['username']
    group_id = get_user_group_id(username)

    if not group_id:
        return redirect(url_for('index'))

    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    expense_date = request.form.get('expense_date')

    if description and amount:
        expense_id = str(uuid.uuid4())
        try:
            created_at = expense_date + 'T00:00:00' if expense_date else datetime.now().isoformat()
            db.collection('expenses').document(expense_id).set({
                'id': expense_id,
                'group_id': group_id,
                'description': description,
                'amount': float(amount),
                'category': category if category else 'Others',
                'paid_by': username,
                'created_at': created_at
            })
        except Exception as e:
            logging.error(f"Add expense error: {e}")

    return redirect(url_for('index'))

@app.route('/delete_expense/<expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))
    
    try:
        db.collection('expenses').document(expense_id).delete()
    except Exception as e:
        logging.error(f"Delete expense error: {e}")
    
    return redirect(url_for('index'))

@app.route('/edit_expense/<expense_id>', methods=['POST'])
@login_required
def edit_expense(expense_id):
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    expense_date = request.form.get('expense_date')

    try:
        update_data = {}
        if description:
            update_data['description'] = description
        if amount:
            update_data['amount'] = float(amount)
        if category:
            update_data['category'] = category
        if expense_date:
            update_data['created_at'] = expense_date + 'T00:00:00'

        if update_data:
            db.collection('expenses').document(expense_id).update(update_data)
    except Exception as e:
        logging.error(f"Edit expense error: {e}")

    return redirect(url_for('index'))

@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    username = session['username']
    group_id = get_user_group_id(username)

    if not group_id:
        return redirect(url_for('index'))

    new_category = request.form.get('new_category', '').strip()
    if new_category:
        try:
            group_ref = db.collection('groups').document(group_id)
            group_doc = group_ref.get()
            if group_doc.exists:
                custom_cats = group_doc.to_dict().get('custom_categories', [])
                if new_category not in custom_cats:
                    custom_cats.append(new_category)
                    group_ref.update({'custom_categories': custom_cats})
        except Exception as e:
            logging.error(f"Add category error: {e}")

    return redirect(url_for('index'))

@app.route('/search')
@login_required
def search_expenses():
    username = session['username']
    group_id = get_user_group_id(username)

    if not group_id:
        return render_template('group_setup.html', username=username)

    query = request.args.get('q', '').lower()
    current_period = get_current_period()
    period_id = request.args.get('period', current_period['id'])
    member_filter = request.args.get('member', '')

    try:
        group_doc = db.collection('groups').document(group_id).get()
        group = group_doc.to_dict() if group_doc.exists else None

        members_ref = db.collection('users').where('group_id', '==', group_id)
        members = [u.to_dict().get('username') for u in members_ref.stream()]

        expenses_ref = db.collection('expenses').where('group_id', '==', group_id)
        all_expenses = [e.to_dict() for e in expenses_ref.stream()]

        expenses_sorted = filter_expenses_by_period(all_expenses, period_id)

        if member_filter:
            expenses_sorted = [e for e in expenses_sorted if e.get('paid_by') == member_filter]

        if query:
            expenses_sorted = [e for e in expenses_sorted if query in e.get('description', '').lower() or query in e.get('category', '').lower()]

        processed = process_expense_data(expenses_sorted)
        custom_cats = get_group_categories(group_id)
        periods = get_periods_options()
        budget = get_group_budget(group_id, period_id)

        return render_template('index.html',
                         expenses=expenses_sorted,
                         total=processed['total'],
                         category_totals=processed['category_totals'],
                         categories=custom_cats,
                         current_period=period_id,
                         periods=periods,
                         members=members,
                         member_filter=member_filter,
                         member_totals=processed['member_totals'],
                         search_query=query,
                         budget=budget,
                         username=username,
                         group_name=group['name'] if group else 'My Group',
                         invite_code=group['invite_code'] if group else 'N/A')
    except Exception as e:
        logging.error(f"Search error: {e}")
        return redirect(url_for('index'))

@app.route('/members')
@login_required
def view_members():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))
    
    username = session['username']
    group_id = get_user_group_id(username)

    if not group_id:
        return redirect(url_for('index'))

    try:
        group_doc = db.collection('groups').document(group_id).get()
        group = group_doc.to_dict() if group_doc.exists else {}

        members_ref = db.collection('users').where('group_id', '==', group_id)
        members = [u.to_dict().get('username') for u in members_ref.stream()]

        return render_template('members.html',
                         members=members,
                         group_name=group.get('name', 'My Group'),
                         username=username,
                         invite_code=group.get('invite_code', 'N/A'))
    except Exception as e:
        logging.error(f"Members error: {e}")
        return redirect(url_for('index'))

@app.route('/leave_group', methods=['POST'])
@login_required
def leave_group():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))
    
    username = session['username']
    group_id = get_user_group_id(username)

    if not group_id:
        return redirect(url_for('index'))

    try:
        db.collection('users').document(username).update({
            'group_id': firestore.DELETE_FIELD
        })
    except Exception as e:
        logging.error(f"Leave group error: {e}")

    return redirect(url_for('index'))

@app.route('/budget', methods=['GET', 'POST'])
@login_required
def budget():
    username = session['username']
    group_id = get_user_group_id(username)
    current_period = get_current_period()
    period_id = request.args.get('period', current_period['id'])

    is_group = request.args.get('type') == 'group'
    budget_id = f'group_{group_id}_{period_id}' if is_group else f'{username}_{period_id}'

    if request.method == 'POST':
        amount = request.form.get('amount')
        if amount:
            try:
                db.collection('budgets').document(budget_id).set({
                    'id': budget_id,
                    'amount': float(amount),
                    'period_id': period_id,
                    'user_id': username,
                    'group_id': group_id if is_group else None,
                    'is_group': is_group
                })
            except Exception as e:
                logging.error(f"Set budget error: {e}")
        return redirect(request.referrer or url_for('index'))

    try:
        budget_doc = db.collection('budgets').document(budget_id).get()
        current_budget = budget_doc.to_dict() if budget_doc.exists else None
    except:
        current_budget = None

    if is_group and group_id:
        try:
            expenses_ref = db.collection('expenses').where('group_id', '==', group_id)
            all_expenses = [e.to_dict() for e in expenses_ref.stream()]
            expenses_sorted = filter_expenses_by_period(all_expenses, period_id)
            total = sum(e.get('amount', 0) for e in expenses_sorted)
        except:
            total = 0
    else:
        try:
            expenses_ref = db.collection('expenses').where('user_id', '==', username)
            all_expenses = [e.to_dict() for e in expenses_ref.stream()]
            expenses_sorted = filter_expenses_by_period(all_expenses, period_id)
            total = sum(e.get('amount', 0) for e in expenses_sorted)
        except:
            total = 0

    return render_template('budget.html',
                         budget=current_budget,
                         spent=total,
                         period_id=period_id,
                         is_group=is_group,
                         username=username,
                         periods=get_periods_options())

@app.route('/export_csv')
@login_required
def export_csv():
    import csv
    import io
    from flask import Response
    username = session['username']
    group_id = get_user_group_id(username)
    current_period = get_current_period()
    period_id = request.args.get('period', current_period['id'])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Description', 'Category', 'Amount', 'Paid By'])

    if group_id:
        expenses_ref = db.collection('expenses').where('group_id', '==', group_id)
        all_expenses = [e.to_dict() for e in expenses_ref.stream()]
    else:
        expenses_ref = db.collection('expenses').where('user_id', '==', username)
        all_expenses = [e.to_dict() for e in expenses_ref.stream()]

    expenses_sorted = filter_expenses_by_period(all_expenses, period_id)

    for e in expenses_sorted:
        writer.writerow([
            e.get('created_at', ''),
            e.get('description', ''),
            e.get('category', ''),
            e.get('amount', 0),
            e.get('paid_by', '')
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=expenses_{period_id}.csv'}
    )

@app.route('/chart_data')
@login_required
def chart_data():
    username = session['username']
    group_id = get_user_group_id(username)
    current_period = get_current_period()
    period_id = request.args.get('period', current_period['id'])
    chart_type = request.args.get('type', 'category')
    view_type = request.args.get('view', 'group')

    if view_type == 'personal' or not group_id:
        expenses_ref = db.collection('expenses').where('user_id', '==', username)
        all_expenses = [e.to_dict() for e in expenses_ref.stream()]
    else:
        expenses_ref = db.collection('expenses').where('group_id', '==', group_id)
        all_expenses = [e.to_dict() for e in expenses_ref.stream()]

    expenses_sorted = filter_expenses_by_period(all_expenses, period_id)

    if chart_type == 'category':
        category_totals = get_period_totals(expenses_sorted)
        labels = list(category_totals.keys())
        values = list(category_totals.values())
    else:
        member_totals = {}
        for e in expenses_sorted:
            p = e.get('paid_by', 'Unknown')
            member_totals[p] = member_totals.get(p, 0) + e.get('amount', 0)
        labels = list(member_totals.keys())
        values = list(member_totals.values())

    return {'labels': labels, 'values': values}

@app.route('/add_split_expense', methods=['POST'])
@login_required
def add_split_expense():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    username = session['username']
    group_id = get_user_group_id(username)

    if not group_id:
        return redirect(url_for('index'))

    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    expense_date = request.form.get('expense_date')
    split_type = request.form.get('split_type', 'equal')
    split_members = request.form.getlist('split_members')

    if description and amount and split_members:
        expense_id = str(uuid.uuid4())
        total_amount = float(amount)
        
        if split_type == 'equal':
            split_amount = total_amount / len(split_members)
            split_data = {member: round(split_amount, 2) for member in split_members}
        else:
            split_data = {}
            remaining = total_amount
            for i, member in enumerate(split_members):
                if i == len(split_members) - 1:
                    split_data[member] = round(remaining, 2)
                else:
                    custom_amount = float(request.form.get(f'custom_{member}', 0))
                    split_data[member] = custom_amount
                    remaining -= custom_amount

        try:
            created_at = expense_date + 'T00:00:00' if expense_date else datetime.now().isoformat()
            db.collection('expenses').document(expense_id).set({
                'id': expense_id,
                'group_id': group_id,
                'description': description,
                'amount': total_amount,
                'category': category if category else 'Others',
                'paid_by': username,
                'created_at': created_at,
                'split_type': split_type,
                'split_data': split_data,
                'split_among': split_members
            })
        except Exception as e:
            logging.error(f"Add split expense error: {e}")

    return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/add_with_image', methods=['POST'])
@login_required
def add_expense_with_image():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    username = session['username']
    group_id = get_user_group_id(username)

    if not group_id:
        return redirect(url_for('index'))

    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    expense_date = request.form.get('expense_date')
    image = request.files.get('image')

    image_filename = None
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            image_filename = f"{uuid.uuid4()}{ext}"
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

    if description and amount:
        expense_id = str(uuid.uuid4())
        try:
            created_at = expense_date + 'T00:00:00' if expense_date else datetime.now().isoformat()
            expense_data = {
                'id': expense_id,
                'group_id': group_id,
                'description': description,
                'amount': float(amount),
                'category': category if category else 'Others',
                'paid_by': username,
                'created_at': created_at
            }
            if image_filename:
                expense_data['image'] = image_filename
            db.collection('expenses').document(expense_id).set(expense_data)
        except Exception as e:
            logging.error(f"Add expense error: {e}")

    return redirect(url_for('index'))

@app.route('/add_personal_with_image', methods=['POST'])
@login_required
def add_personal_expense_with_image():
    db_error = check_db()
    if db_error:
        return redirect(url_for('login'))

    username = session['username']
    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    expense_date = request.form.get('expense_date')
    image = request.files.get('image')

    image_filename = None
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            image_filename = f"{uuid.uuid4()}{ext}"
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

    if description and amount:
        expense_id = str(uuid.uuid4())
        try:
            created_at = expense_date + 'T00:00:00' if expense_date else datetime.now().isoformat()
            expense_data = {
                'id': expense_id,
                'user_id': username,
                'description': description,
                'amount': float(amount),
                'category': category if category else 'Others',
                'paid_by': username,
                'created_at': created_at
            }
            if image_filename:
                expense_data['image'] = image_filename
            db.collection('expenses').document(expense_id).set(expense_data)
        except Exception as e:
            logging.error(f"Add personal expense error: {e}")

    return redirect(url_for('personal'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)
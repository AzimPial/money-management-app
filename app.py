from flask import Flask, render_template, request, redirect, url_for
import json
import os

app = Flask(__name__)

# Simple JSON storage
DATA_FILE = 'expenses.json'

def load_expenses():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return []

def save_expenses(expenses):
    with open(DATA_FILE, 'w') as f:
        json.dump(expenses, f, indent=4)

@app.route('/')
def index():
    expenses = load_expenses()
    total = sum(float(e['amount']) for e in expenses)
    return render_template('index.html', expenses=expenses, total=total)

@app.route('/add', methods=['POST'])
def add_expense():
    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    
    if description and amount:
        expenses = load_expenses()
        expenses.append({
            'description': description,
            'amount': amount,
            'category': category or 'General'
        })
        save_expenses(expenses)
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)

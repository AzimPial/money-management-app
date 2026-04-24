from flask import Flask, render_template, request, redirect, url_for
import json
import os
import logging

app = Flask(__name__)

# Set up logging to catch errors
logging.basicConfig(level=logging.INFO)

DATA_FILE = 'expenses.json'

def load_expenses():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                content = f.read()
                if not content:
                    return []
                return json.loads(content)
    except Exception as e:
        app.logger.error(f"Error loading expenses: {e}")
        return []
    return []

def save_expenses(expenses):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(expenses, f, indent=4)
    except Exception as e:
        app.logger.error(f"Error saving expenses: {e}")

@app.route('/')
def index():
    try:
        expenses = load_expenses()
        total = 0
        for e in expenses:
            try:
                total += float(e.get('amount', 0))
            except (ValueError, TypeError):
                continue
        return render_template('index.html', expenses=expenses, total=total)
    except Exception as e:
        app.logger.error(f"Index page error: {e}")
        return "Internal Server Error", 500

@app.route('/add', methods=['POST'])
def add_expense():
    try:
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
    except Exception as e:
        app.logger.error(f"Add expense error: {e}")
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)

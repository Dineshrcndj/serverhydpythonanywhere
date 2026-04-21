import os
import random
import sqlite3
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from dotenv import load_dotenv
from flask_cors import CORS




load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
app.permanent_session_lifetime = timedelta(days=7)

DATABASE_PATH = 'data.sqlite3'

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


# Add this after creating the app
CORS(app, origins='*', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'], allow_headers=['Content-Type'])

# Or more specifically for your API routes
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def send_telegram_message(text, parse_mode='Markdown'):
    """Send message to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(url, json={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text,
            'parse_mode': parse_mode
        }, timeout=10)
        return response.ok
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

# ============= DATABASE INITIALIZATION =============
def init_db():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount TEXT,
            amount_formatted TEXT,
            trid TEXT,
            dtid TEXT,
            banktimestamp TEXT,
            timestamp INTEGER,
            date TEXT,
            website TEXT,
            fullurl TEXT,
            yourshare TEXT,
            yourshare_formatted TEXT,
            originalstatus TEXT,
            modifiedstatus TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            phone_number TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount TEXT,
            description TEXT,
            timestamp INTEGER,
            date TEXT,
            verified_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            phone_number TEXT
        )
    ''')
    
    db.commit()

with app.app_context():
    init_db()

# ============= LOGIN ROUTES =============
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT * FROM users WHERE phone_number = ? AND password = ? AND is_active = 1', (phone, password))
            result = cursor.fetchone()
            
            if result:
                user = dict(result)
                session['user'] = {
                    'id': user['id'],
                    'phone': user['phone_number'],
                    'name': user.get('full_name', 'User'),
                    'role': user.get('role', 'user')
                }
                session.permanent = True
                
                if user.get('role') == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('user_dashboard'))
            else:
                return render_template('login.html', error='Invalid phone or password')
        except Exception as e:
            return render_template('login.html', error=f'Login error: {str(e)}')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user' in session:
        if session['user']['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
def user_dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    if session['user']['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    return render_template('user_dashboard.html', user=session['user'])

@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))
    
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id, phone_number, full_name FROM users WHERE is_active = 1 ORDER BY full_name')
        users = [dict(row) for row in cursor.fetchall()]
        return render_template('admin_dashboard.html', user=session['user'], users=users)
    except Exception as e:
        return f"Error loading admin panel: {e}"

# ============= ADD TRANSACTION ROUTE (FOR TAMPERMONKEY) =============
@app.route('/api/add-transaction', methods=['POST'])
def add_transaction():
    """Add a new transaction from Tampermonkey script or Telegram parser"""
    db = None  # Initialize db variable
    
    try:
        data = request.json
        print(f"📥 Received transaction data: {data}")
        
        # Get database connection
        db = get_db()
        cursor = db.cursor()
        
        phone_number = data.get('phone_number')
        user_name = data.get('user_name')
        amount = data.get('amount')
        amount_formatted = data.get('amount_formatted')
        trid = data.get('trid')
        dtid = data.get('dtid')
        banktimestamp = data.get('banktimestamp')
        timestamp = data.get('timestamp', int(datetime.now().timestamp() * 1000))
        
        # Fix date format - handle potential issues
        date_value = data.get('date')
        if not date_value:
            date_value = datetime.now().strftime('%m/%d/%Y')
        
        website = data.get('website', 'prdcfms.apcfss.in')
        fullurl = data.get('fullurl')
        yourshare = data.get('yourshare')
        yourshare_formatted = data.get('yourshare_formatted')
        originalstatus = data.get('originalstatus', 'Failure')
        modifiedstatus = data.get('modifiedstatus', 'Success')
        
        # Validate required fields
        if not phone_number:
            return jsonify({'success': False, 'error': 'Phone number is required'}), 400
        
        if not amount or float(amount) <= 0:
            return jsonify({'success': False, 'error': 'Valid amount is required'}), 400
        
        # Check if user exists, if not create them
        cursor.execute('SELECT * FROM users WHERE phone_number = ?', (phone_number,))
        existing_user = cursor.fetchone()
        
        if not existing_user:
            print(f"📝 Creating new user for phone: {phone_number}")
            cursor.execute('''
                INSERT INTO users (phone_number, password, full_name, role, is_active)
                VALUES (?, ?, ?, ?, ?)
            ''', (phone_number, 'user123', user_name or 'New User', 'user', True))
            db.commit()
            print(f"✅ User created successfully")
        
        # Clean up amount formatting - remove ₹ symbol if present in wrong place
        if amount_formatted and amount_formatted.startswith('?'):
            amount_formatted = amount_formatted.replace('?', '₹')
        
        # Insert transaction
        cursor.execute('''
            INSERT INTO transactions (
                amount, amount_formatted, trid, dtid, banktimestamp, 
                timestamp, date, website, fullurl, yourshare, 
                yourshare_formatted, originalstatus, modifiedstatus, phone_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(amount),
            amount_formatted or f"₹{amount}",
            str(trid),
            str(dtid) if dtid else None,
            str(banktimestamp) if banktimestamp else None,
            int(timestamp),
            str(date_value),
            str(website),
            str(fullurl) if fullurl else None,
            str(yourshare) if yourshare else str(float(amount) * 0.5),
            yourshare_formatted or f"₹{float(amount) * 0.5:.2f}",
            str(originalstatus),
            str(modifiedstatus),
            str(phone_number)
        ))
        
        db.commit()
        transaction_id = cursor.lastrowid
        
        print(f"✅ Transaction {transaction_id} added successfully for phone: {phone_number}")
        
        # Send Telegram notification (optional, non-blocking)
        try:
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                message = f"""🔔 *New Transaction Added via API*

💰 *Amount:* ₹{amount}
👤 *User:* {user_name or 'Unknown'} ({phone_number})
🆔 *TRID:* {trid}
🆔 *DTID:* {dtid or 'N/A'}
📍 *Website:* {website}
⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Status:* {modifiedstatus}"""
                
                import threading
                threading.Thread(target=send_telegram_message, args=(message,)).start()
        except Exception as e:
            print(f"Telegram notification error: {e}")
        
        return jsonify({
            'success': True,
            'message': 'Transaction added successfully',
            'transaction_id': transaction_id
        })
        
    except Exception as e:
        print(f"❌ Error adding transaction: {str(e)}")
        if db:
            try:
                db.rollback()
            except:
                pass
        return jsonify({'success': False, 'error': str(e)}), 500
    

# ============= OTHER API ROUTES =============
@app.route('/api/user-data')
def get_user_data():
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    phone = session['user']['phone']
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT * FROM transactions WHERE phone_number = ? ORDER BY timestamp DESC', (phone,))
        transactions = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('SELECT * FROM withdrawals WHERE phone_number = ? OR phone_number IS NULL ORDER BY timestamp DESC', (phone,))
        withdrawals = [dict(row) for row in cursor.fetchall()]
        
        total_amount = sum(float(t.get('amount', 0)) for t in transactions)
        total_withdrawn = sum(float(w.get('amount', 0)) for w in withdrawals)
        your_share = total_amount * 0.5
        remaining = your_share - total_withdrawn
        
        return jsonify({
            'success': True,
            'transactions': transactions,
            'withdrawals': withdrawals,
            'totals': {
                'totalAmount': total_amount,
                'yourShare': your_share,
                'totalWithdrawn': total_withdrawn,
                'remaining': remaining
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin-data/<phone>')
def get_admin_data(phone):
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT * FROM transactions WHERE phone_number = ? ORDER BY timestamp DESC', (phone,))
        transactions = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('SELECT * FROM withdrawals WHERE phone_number = ? OR phone_number IS NULL ORDER BY timestamp DESC', (phone,))
        withdrawals = [dict(row) for row in cursor.fetchall()]
        
        total_amount = sum(float(t.get('amount', 0)) for t in transactions)
        total_withdrawn = sum(float(w.get('amount', 0)) for w in withdrawals)
        your_share = total_amount * 0.5
        remaining = your_share - total_withdrawn
        
        cursor.execute('SELECT full_name, phone_number FROM users WHERE phone_number = ?', (phone,))
        user_info = cursor.fetchone()
        
        return jsonify({
            'success': True,
            'transactions': transactions,
            'withdrawals': withdrawals,
            'user': dict(user_info) if user_info else {'phone': phone},
            'totals': {
                'totalAmount': total_amount,
                'yourShare': your_share,
                'totalWithdrawn': total_withdrawn,
                'remaining': remaining
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/request-otp', methods=['POST'])
def request_otp():
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.json
    amount = float(data.get('amount', 0))
    description = data.get('description', 'Withdrawal')
    
    if amount <= 0:
        return jsonify({'success': False, 'error': 'Invalid amount'}), 400
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT amount FROM transactions WHERE phone_number = ?', (session['user']['phone'],))
        transactions = cursor.fetchall()
        
        cursor.execute('SELECT amount FROM withdrawals')
        withdrawals = cursor.fetchall()
        
        total_amount = sum(float(t['amount']) for t in transactions)
        total_withdrawn = sum(float(w['amount']) for w in withdrawals)
        your_share = total_amount * 0.5
        remaining = your_share - total_withdrawn
        
        if amount > remaining:
            return jsonify({'success': False, 'error': f'Insufficient balance'}), 400
        
        otp = str(random.randint(100000, 999999))
        
        session['current_otp'] = otp
        session['withdrawal_data'] = {'amount': amount, 'description': description, 'phone_number': session['user']['phone']}
        session['otp_expiry'] = (datetime.now() + timedelta(minutes=5)).isoformat()
        
        message = f"""🔐 *Withdrawal OTP Request*
💰 Amount: ₹{amount}
📝 {description}
👤 User: {session['user']['phone']}
🔑 OTP: *{otp}*
⏰ Expires in 5 minutes"""
        
        if send_telegram_message(message):
            return jsonify({'success': True, 'message': 'OTP sent to Telegram'})
        else:
            return jsonify({'success': False, 'error': 'Failed to send OTP'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.json
    entered_otp = data.get('otp', '')
    
    stored_otp = session.get('current_otp')
    expiry = session.get('otp_expiry')
    withdrawal_data = session.get('withdrawal_data')
    
    if not stored_otp or not withdrawal_data:
        return jsonify({'success': False, 'error': 'No OTP request found'}), 400
    
    if datetime.now() > datetime.fromisoformat(expiry):
        session.pop('current_otp', None)
        session.pop('withdrawal_data', None)
        session.pop('otp_expiry', None)
        return jsonify({'success': False, 'error': 'OTP expired'}), 400
    
    if entered_otp != stored_otp:
        return jsonify({'success': False, 'error': 'Invalid OTP'}), 400
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        amount = withdrawal_data['amount']
        description = withdrawal_data['description']
        phone_number = withdrawal_data.get('phone_number', session['user']['phone'])
        now = datetime.now()
        
        cursor.execute('''
            INSERT INTO withdrawals (amount, description, timestamp, date, verified_by, phone_number)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (str(amount), description, int(now.timestamp() * 1000), now.strftime('%Y-%m-%d'), 'OTP', phone_number))
        db.commit()
        
        session.pop('current_otp', None)
        session.pop('withdrawal_data', None)
        session.pop('otp_expiry', None)
        
        return jsonify({'success': True, 'message': 'Withdrawal completed successfully'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cancel-otp', methods=['POST'])
def cancel_otp():
    session.pop('current_otp', None)
    session.pop('withdrawal_data', None)
    session.pop('otp_expiry', None)
    return jsonify({'success': True, 'message': 'OTP cancelled'})

# ============= DATABASE MANAGEMENT ROUTES =============
@app.route('/admin/database')
def database_manager():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row['name'] for row in cursor.fetchall()]
    
    return render_template('database_manager.html', user=session['user'], tables=tables)

@app.route('/api/database/tables')
def get_tables():
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row['name'] for row in cursor.fetchall()]
        return jsonify({'success': True, 'tables': tables})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/database/table/<table_name>')
def get_table_data(table_name):
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [{'name': row['name'], 'type': row['type']} for row in cursor.fetchall()]
        
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY id DESC")
        rows = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({'success': True, 'columns': columns, 'rows': rows, 'table_name': table_name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/database/update', methods=['POST'])
def update_row():
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    data = request.json
    table_name = data.get('table_name')
    row_id = data.get('id')
    updates = data.get('updates', {})
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [row_id]
        
        cursor.execute(f"UPDATE {table_name} SET {set_clause} WHERE id = ?", values)
        db.commit()
        
        return jsonify({'success': True, 'message': 'Row updated successfully'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/database/insert', methods=['POST'])
def insert_row():
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    data = request.json
    table_name = data.get('table_name')
    row_data = data.get('data', {})
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        columns = ', '.join(row_data.keys())
        placeholders = ', '.join(['?' for _ in row_data])
        values = list(row_data.values())
        
        cursor.execute(f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})", values)
        db.commit()
        
        return jsonify({'success': True, 'message': 'Row inserted successfully', 'id': cursor.lastrowid})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/database/delete', methods=['POST'])
def delete_row():
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    data = request.json
    table_name = data.get('table_name')
    row_id = data.get('id')
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (row_id,))
        db.commit()
        
        return jsonify({'success': True, 'message': 'Row deleted successfully'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    

import schedule
import threading
import time
import io
from datetime import datetime

tbot="8083496802:AAE3h44C7ydCWOjAQyE5kCD3wbBbymnugk8"


# ============= AUTO BACKUP SYSTEM =============

def generate_sql_backup():
    """Generate SQL backup from database"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row['name'] for row in cursor.fetchall()]
        
        sql_lines = []
        sql_lines.append("-- SQLite Database Backup")
        sql_lines.append(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        sql_lines.append(f"-- Database: {DATABASE_PATH}")
        sql_lines.append("")
        
        for table in tables:
            # Get CREATE TABLE statement
            cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")
            create_sql = cursor.fetchone()
            if create_sql and create_sql[0]:
                sql_lines.append(create_sql[0] + ";")
                sql_lines.append("")
            
            # Get all data
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            
            if rows:
                # Get column names
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [row['name'] for row in cursor.fetchall()]
                
                for row in rows:
                    values = []
                    for col in columns:
                        val = row[col]
                        if val is None:
                            values.append("NULL")
                        elif isinstance(val, (int, float)):
                            values.append(str(val))
                        else:
                            # Escape single quotes and handle special characters
                            val_str = str(val).replace("'", "''")
                            values.append(f"'{val_str}'")
                    
                    insert_sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(values)});"
                    sql_lines.append(insert_sql)
                
                sql_lines.append("")
        
        return "\n".join(sql_lines)
        
    except Exception as e:
        print(f"❌ Backup generation error: {e}")
        return None

def send_file_to_telegram(file_content, filename):
    """Send a file to Telegram"""
    if not tbot or not TELEGRAM_CHAT_ID:
        print("❌ Telegram credentials not configured")
        return False
    
    try:
        import requests
        
        # First, get file size
        file_size = len(file_content.encode('utf-8'))
        max_size = 50 * 1024 * 1024  # 50MB Telegram limit
        
        if file_size > max_size:
            print(f"⚠️ Backup file too large ({file_size} bytes). Compressing...")
            # For large files, we'll send as text in chunks or just send summary
            return send_large_backup_summary(file_size)
        
        url = f"https://api.telegram.org/bot{tbot}/sendDocument"
        
        # Create multipart form data
        files = {
            'document': (filename, io.BytesIO(file_content.encode('utf-8')), 'application/sql')
        }
        
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'caption': f"📦 *Daily Database Backup*\n\n📅 Date: {datetime.now().strftime('%Y-%m-%d')}\n⏰ Time: {datetime.now().strftime('%H:%M:%S')}\n📁 File: {filename}\n📊 Size: {file_size/1024:.2f} KB"
        }
        
        response = requests.post(url, files=files, data=data, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ Backup sent to Telegram: {filename}")
            return True
        else:
            print(f"❌ Telegram API error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending file to Telegram: {e}")
        return False

def send_large_backup_summary(file_size):
    """Send summary for large backups instead of full file"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get database statistics
        cursor.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM transactions")
        transaction_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM withdrawals")
        withdrawal_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT SUM(amount) as total FROM transactions")
        total_amount = cursor.fetchone()['total'] or 0
        
        message = f"""⚠️ *Large Backup Notification*

📦 Backup file size: {file_size/1024/1024:.2f} MB (exceeds Telegram limit)

📊 *Database Statistics:*
• Users: {user_count}
• Transactions: {transaction_count}
• Withdrawals: {withdrawal_count}
• Total Amount: ₹{float(total_amount):.2f}

📅 Date: {datetime.now().strftime('%Y-%m-%d')}

💡 *Recommendation:* 
- Access backup via admin panel at /admin/export-sql
- Or reduce database size by archiving old records

✅ Auto-backup process completed (summary sent)"""
        
        return send_telegram_message(message, 'Markdown')
        
    except Exception as e:
        print(f"Error sending large backup summary: {e}")
        return False

def perform_auto_backup():
    """Perform automatic database backup"""
    print(f"\n🔄 Starting auto backup at {datetime.now()}")
    
    try:
        # Generate backup
        backup_content = generate_sql_backup()
        
        if backup_content:
            # Create filename with date
            filename = f"database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            
            # Send to Telegram
            success = send_file_to_telegram(backup_content, filename)
            
            if success:
                print(f"✅ Auto backup completed successfully at {datetime.now()}")
                # Also log to a backup log file
                log_backup_success()
            else:
                print(f"❌ Auto backup failed at {datetime.now()}")
                log_backup_failure()
        else:
            print(f"❌ Failed to generate backup content")
            
    except Exception as e:
        print(f"❌ Auto backup error: {e}")

def log_backup_success():
    """Log successful backup to file"""
    try:
        with open('backup_log.txt', 'a') as f:
            f.write(f"SUCCESS | {datetime.now()} | Backup sent to Telegram\n")
    except:
        pass

def log_backup_failure():
    """Log failed backup to file"""
    try:
        with open('backup_log.txt', 'a') as f:
            f.write(f"FAILURE | {datetime.now()} | Backup failed\n")
    except:
        pass

def run_scheduler():
    """Run the scheduler in a background thread"""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_backup_scheduler():
    """Start the backup scheduler"""
    # Schedule backup at midnight every day
    schedule.every().day.at("00:00").do(perform_auto_backup)
    
    # Optional: Also schedule a backup at noon
    # schedule.every().day.at("12:00").do(perform_auto_backup)
    
    print("✅ Backup scheduler started - Will backup daily at midnight (00:00)")
    print(f"📅 Next backup: {schedule.next_run()}")
    
    # Run scheduler in background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

# ============= MANUAL BACKUP ROUTE =============

@app.route('/admin/backup-now')
def manual_backup():
    """Manually trigger a backup"""
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        perform_auto_backup()
        return jsonify({'success': True, 'message': 'Backup triggered and sent to Telegram'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/backup-status')
def backup_status():
    """Get backup status"""
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        # Read backup log
        backup_log = []
        try:
            with open('backup_log.txt', 'r') as f:
                backup_log = f.readlines()[-10:]  # Last 10 entries
        except:
            backup_log = ["No backup history found"]
        
        next_backup = str(schedule.next_run()) if schedule.next_run() else "Not scheduled"
        
        return jsonify({
            'success': True,
            'next_backup': next_backup,
            'backup_history': backup_log,
            'status': 'active'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= START THE SCHEDULER =============
# Start the backup scheduler when the app starts
# Only start if not in debug mode or use a flag
if not app.debug:  # Don't run scheduler in debug mode
    start_backup_scheduler()
else:
    print("⚠️ Backup scheduler not started (debug mode)")
    print("   To test backup, visit /admin/backup-now")

if __name__ == '__main__':
    app.run(debug=True, port=5000)
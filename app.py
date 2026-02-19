import os
import random
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
app.permanent_session_lifetime = timedelta(days=7)

# Initialize Supabase
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Telegram configuration (only used for OTP now, no diagnostics)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def format_currency(amount):
    """Format amount as Indian Rupees"""
    return f"₹{float(amount or 0):.2f}"

def send_telegram_message(text, parse_mode='Markdown'):
    """Send message to Telegram (only for OTP)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text,
            'parse_mode': parse_mode
        }, timeout=10)
        return response.ok
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

# ============= LOGIN ROUTES =============

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        
        try:
            # Direct query with plain text password (as requested)
            result = supabase.table('users')\
                .select('*')\
                .eq('phone_number', phone)\
                .eq('password', password)\
                .eq('is_active', True)\
                .execute()
            
            if result.data and len(result.data) > 0:
                user = result.data[0]
                session['user'] = {
                    'id': user['id'],
                    'phone': user['phone_number'],
                    'name': user.get('full_name', 'User'),
                    'role': user.get('role', 'user')
                }
                session.permanent = True
                
                # Redirect based on role
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
    """Logout user"""
    session.pop('user', None)
    return redirect(url_for('login'))

# ============= USER DASHBOARD =============

@app.route('/')
def index():
    """Redirect to login or dashboard"""
    if 'user' in session:
        if session['user']['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
def user_dashboard():
    """User dashboard - shows only their data"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if session['user']['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    return render_template('user_dashboard.html', user=session['user'])

# ============= ADMIN DASHBOARD =============

@app.route('/admin')
def admin_dashboard():
    """Admin dashboard - can view any user's data"""
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))
    
    try:
        # Get all users for dropdown
        users = supabase.table('users')\
            .select('id, phone_number, full_name')\
            .eq('is_active', True)\
            .order('full_name')\
            .execute()
        
        return render_template('admin_dashboard.html', 
                             user=session['user'],
                             users=users.data)
    except Exception as e:
        return f"Error loading admin panel: {e}"

# ============= API ROUTES =============

@app.route('/api/user-data')
def get_user_data():
    """Get data for logged-in user"""
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    phone = session['user']['phone']
    
    try:
        # Get user's transactions only
        transactions = supabase.table('transactions')\
            .select('*')\
            .eq('phone_number', phone)\
            .order('timestamp', desc=True)\
            .execute()
        
        # Get user's withdrawals
        withdrawals = supabase.table('withdrawals')\
            .select('*')\
            .order('timestamp', desc=True)\
            .execute()
        
        # Calculate totals
        total_amount = sum(float(t.get('amount', 0)) for t in transactions.data)
        total_withdrawn = sum(float(w.get('amount', 0)) for w in withdrawals.data)
        your_share = total_amount * 0.5
        remaining = your_share - total_withdrawn
        
        return jsonify({
            'success': True,
            'transactions': transactions.data,
            'withdrawals': withdrawals.data,
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
    """Admin gets data for specific user"""
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        # Get selected user's transactions
        transactions = supabase.table('transactions')\
            .select('*')\
            .eq('phone_number', phone)\
            .order('timestamp', desc=True)\
            .execute()
        
        # Get all withdrawals (these are global)
        withdrawals = supabase.table('withdrawals')\
            .select('*')\
            .order('timestamp', desc=True)\
            .execute()
        
        # Calculate totals for this user
        total_amount = sum(float(t.get('amount', 0)) for t in transactions.data)
        total_withdrawn = sum(float(w.get('amount', 0)) for w in withdrawals.data)
        your_share = total_amount * 0.5
        remaining = your_share - total_withdrawn
        
        # Get user info
        user_info = supabase.table('users')\
            .select('full_name, phone_number')\
            .eq('phone_number', phone)\
            .execute()
        
        return jsonify({
            'success': True,
            'transactions': transactions.data,
            'withdrawals': withdrawals.data,
            'user': user_info.data[0] if user_info.data else {'phone': phone},
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
    """Request OTP for withdrawal (no diagnostics)"""
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.json
    amount = float(data.get('amount', 0))
    description = data.get('description', 'Withdrawal')
    
    if amount <= 0:
        return jsonify({'success': False, 'error': 'Invalid amount'}), 400
    
    try:
        # Get current totals for logged-in user
        transactions = supabase.table('transactions')\
            .select('amount')\
            .eq('phone_number', session['user']['phone'])\
            .execute()
        
        withdrawals = supabase.table('withdrawals').select('amount').execute()
        
        total_amount = sum(float(t.get('amount', 0)) for t in transactions.data)
        total_withdrawn = sum(float(w.get('amount', 0)) for w in withdrawals.data)
        your_share = total_amount * 0.5
        remaining = your_share - total_withdrawn
        
        if amount > remaining:
            return jsonify({
                'success': False, 
                'error': f'Insufficient balance. Available: {format_currency(remaining)}'
            }), 400
        
        # Generate OTP
        otp = str(random.randint(100000, 999999))
        
        # Store in session
        session['current_otp'] = otp
        session['withdrawal_data'] = {'amount': amount, 'description': description}
        session['otp_expiry'] = (datetime.now() + timedelta(minutes=5)).isoformat()
        
        # Send OTP via Telegram (only OTP, no diagnostics)
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
    """Verify OTP and create withdrawal"""
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.json
    entered_otp = data.get('otp', '')
    
    # Check OTP from session
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
    
    # Create withdrawal
    try:
        amount = withdrawal_data['amount']
        description = withdrawal_data['description']
        now = datetime.now()
        
        # Insert withdrawal
        withdrawal_data_supabase = {
            'amount': amount,
            'description': description,
            'timestamp': int(now.timestamp() * 1000),
            'date': now.strftime('%Y-%m-%d'),
            'verified_by': 'OTP'
        }
        
        supabase.table('withdrawals').insert(withdrawal_data_supabase).execute()
        
        # Clear session data
        session.pop('current_otp', None)
        session.pop('withdrawal_data', None)
        session.pop('otp_expiry', None)
        
        return jsonify({'success': True, 'message': 'Withdrawal completed successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cancel-otp', methods=['POST'])
def cancel_otp():
    """Cancel current OTP request"""
    session.pop('current_otp', None)
    session.pop('withdrawal_data', None)
    session.pop('otp_expiry', None)
    return jsonify({'success': True, 'message': 'OTP cancelled'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
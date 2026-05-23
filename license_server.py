from flask import Flask, request, jsonify
import json
import secrets
import requests
from datetime import datetime, timedelta
import base64
import os
import string
from pathlib import Path

app = Flask(__name__)

# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_USERNAME = "Yunus852123"
GITHUB_REPO = "twitch-checker-licenses"
GITHUB_FILE = "licenses.json"
SELLAUTH_SECRET = os.environ.get('SELLAUTH_SECRET', '')

USERS_FILE = Path('users.json')
ADMIN_KEY = "TwitchChecker2026AdminKey_SecurePassword"  # Change this to your own secret key

# ═══════════════════════════════════════════════════════
# USER MANAGEMENT
# ═══════════════════════════════════════════════════════

def generate_username():
    """Generate random username"""
    return f"user_{secrets.token_hex(4)}"

def generate_password():
    """Generate random password"""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(12))

def load_users():
    """Load users from file"""
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text())
    return []

def save_users(users):
    """Save users to file"""
    USERS_FILE.write_text(json.dumps(users, indent=2))

def create_user(email, license_key):
    """Create new user account"""
    username = generate_username()
    password = generate_password()
    
    user = {
        'username': username,
        'password': password,
        'email': email,
        'license_key': license_key,
        'hwid': None,
        'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'active': True,
        'last_login': None
    }
    
    users = load_users()
    users.append(user)
    save_users(users)
    
    return username, password

# ═══════════════════════════════════════════════════════
# LICENSE GENERATION
# ═══════════════════════════════════════════════════════

def generate_license_key():
    """Generate random license key"""
    return '-'.join([secrets.token_hex(4).upper() for _ in range(4)])

def create_license(duration_days=30, customer_email="", customer_name=""):
    """Create a new license"""
    license_key = generate_license_key()
    
    if duration_days == 0:
        expiry = "lifetime"
    else:
        expiry = (datetime.now() + timedelta(days=duration_days)).strftime('%Y-%m-%d')
    
    license_data = {
        'key': license_key,
        'hwid': None,
        'expiry': expiry,
        'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'note': f"{customer_name} ({customer_email})",
        'active': True
    }
    
    return license_data

# ═══════════════════════════════════════════════════════
# GITHUB FUNCTIONS
# ═══════════════════════════════════════════════════════

def get_github_file():
    """Download current licenses.json from GitHub"""
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        content = response.json()
        file_content = base64.b64decode(content['content']).decode('utf-8')
        return json.loads(file_content), content['sha']
    else:
        return [], None

def update_github_file(licenses, sha):
    """Upload updated licenses.json to GitHub"""
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    content = base64.b64encode(json.dumps(licenses, indent=2).encode()).decode()
    
    data = {
        'message': f'Add new license - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        'content': content,
        'sha': sha
    }
    
    response = requests.put(url, headers=headers, json=data)
    return response.status_code == 200

# ═══════════════════════════════════════════════════════
# WEBHOOK ENDPOINT
# ═══════════════════════════════════════════════════════

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Sellauth webhook"""
    try:
        data = request.json
        
        # Log the webhook for debugging
        print("WEBHOOK RECEIVED:")
        print(json.dumps(data, indent=2))
        
        # Extract customer info from Sellauth structure
        customer = data.get('customer', {})
        item = data.get('item', {})
        variant = item.get('variant', {}) if item else {}
        
        customer_email = customer.get('email', 'no-email-provided')
        customer_name = customer_email.split('@')[0]
        
        # Determine license duration based on variant name
        variant_name = variant.get('name', '').lower() if variant else ''

        if 'lifetime' in variant_name:
            duration_days = 0
        elif '30 days' in variant_name or '30 day' in variant_name:
            duration_days = 30
        else:
            duration_days = 30
        
        # Generate license
        new_license = create_license(duration_days, customer_email, customer_name)
        
        # Get current licenses from GitHub
        licenses, sha = get_github_file()
        
        # Add new license
        licenses.append(new_license)
        
        # Upload to GitHub
        if update_github_file(licenses, sha):
            print(f"✓ License created: {new_license['key']} for {customer_email}")
            
            # Create user account
            username, password = create_user(customer_email, new_license['key'])
            
            return jsonify({
                'success': True,
                'license_key': new_license['key'],
                'username': username,
                'password': password,
                'message': f'License Key: {new_license["key"]}\nUsername: {username}\nPassword: {password}'
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to update GitHub'}), 500
    
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})

# ═══════════════════════════════════════════════════════
# LOGIN ENDPOINT WITH HWID LOCKING
# ═══════════════════════════════════════════════════════

@app.route('/login', methods=['POST'])
def login():
    """Authenticate user with HWID locking"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        hwid = data.get('hwid')
        
        # Load users
        users = load_users()
        
        for i, user in enumerate(users):
            if user['username'] == username and user['password'] == password:
                if not user['active']:
                    return jsonify({'error': 'Account disabled'}), 403
                
                # HWID locking check
                user_hwid = user.get('hwid')
                
                if user_hwid is None:
                    # First login - bind to this HWID
                    user['hwid'] = hwid
                    user['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    users[i] = user
                    save_users(users)
                    print(f"✓ Account {username} bound to HWID {hwid[:8]}...")
                    
                elif user_hwid != hwid:
                    # Trying to login from different computer
                    return jsonify({'error': 'Account already activated on another computer'}), 403
                else:
                    # Same computer - update last login
                    user['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    users[i] = user
                    save_users(users)
                
                # Verify their license is still valid
                license_key = user['license_key']
                licenses, _ = get_github_file()
                
                for lic in licenses:
                    if lic['key'] == license_key:
                        if not lic['active']:
                            return jsonify({'error': 'License expired'}), 403
                        
                        # Check expiry
                        if lic['expiry'] != 'lifetime':
                            expiry_date = datetime.strptime(lic['expiry'], '%Y-%m-%d')
                            if datetime.now() > expiry_date:
                                return jsonify({'error': 'License expired'}), 403
                        
                        # Generate session token
                        session_token = secrets.token_hex(32)
                        
                        return jsonify({
                            'success': True,
                            'session_token': session_token,
                            'license_key': license_key,
                            'expiry': lic['expiry']
                        })
                
                return jsonify({'error': 'License not found'}), 404
        
        return jsonify({'error': 'Invalid credentials'}), 401
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ═══════════════════════════════════════════════════════
# HWID RESET ENDPOINT
# ═══════════════════════════════════════════════════════

@app.route('/reset-hwid', methods=['POST'])
def reset_hwid():
    """Reset user's HWID - for support/upgrades"""
    try:
        data = request.json
        username = data.get('username')
        admin_key = data.get('admin_key')
        
        # Admin authentication
        if admin_key != ADMIN_KEY:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Load users
        users = load_users()
        
        for i, user in enumerate(users):
            if user['username'] == username:
                # Reset HWID
                old_hwid = user.get('hwid', 'None')
                user['hwid'] = None
                users[i] = user
                save_users(users)
                
                print(f"✓ HWID reset for {username} (was: {old_hwid[:8] if old_hwid else 'None'}...)")
                
                return jsonify({
                    'success': True,
                    'message': f'HWID reset for {username}. They can login from new PC now.'
                })
        
        return jsonify({'error': 'User not found'}), 404
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ═══════════════════════════════════════════════════════
# MANUAL LICENSE CREATION
# ═══════════════════════════════════════════════════════

@app.route('/create-license', methods=['POST'])
def create_license_manual():
    """Manually create a license (for testing)"""
    try:
        data = request.json
        customer_email = data.get('email', 'test@test.com')
        customer_name = data.get('name', 'Test User')
        duration_days = data.get('days', 30)
        
        new_license = create_license(duration_days, customer_email, customer_name)
        
        licenses, sha = get_github_file()
        licenses.append(new_license)
        
        if update_github_file(licenses, sha):
            # Also create user
            username, password = create_user(customer_email, new_license['key'])
            
            return jsonify({
                'success': True,
                'license_key': new_license['key'],
                'username': username,
                'password': password
            })
        else:
            return jsonify({'success': False, 'message': 'GitHub update failed'}), 500
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/update-hwid', methods=['POST'])
def update_hwid():
    """Update license HWID after activation"""
    try:
        data = request.json
        license_key = data.get('license_key')
        hwid = data.get('hwid')
        
        # Get current licenses from GitHub
        licenses, sha = get_github_file()
        
        # Find and update the license
        updated = False
        for lic in licenses:
            if lic['key'] == license_key:
                lic['hwid'] = hwid
                updated = True
                break
        
        if updated:
            # Push back to GitHub
            if update_github_file(licenses, sha):
                return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'License not found'}), 404
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

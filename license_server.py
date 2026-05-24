from flask import Flask, request, jsonify
import json
import secrets
import requests
from datetime import datetime, timedelta
import base64
import os

app = Flask(__name__)

# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_USERNAME = "Yunus852123"
GITHUB_REPO = "twitch-checker-licenses"
GITHUB_FILE = "licenses.json"

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
        
        print("WEBHOOK RECEIVED:")
        print(json.dumps(data, indent=2))
        
        # Extract customer info
        customer = data.get('customer', {})
        item = data.get('item', {})
        variant = item.get('variant', {}) if item else {}
        
        customer_email = customer.get('email', 'no-email-provided')
        customer_name = customer_email.split('@')[0]
        
        # Determine duration
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
            
            # Simple delivery message
            expiry_text = "Never (Lifetime)" if duration_days == 0 else new_license['expiry']
            
            delivery_message = f"""LICENSE KEY: {new_license['key']}
EXPIRES: {expiry_text}

Download TwitchChecker.exe from the Files section.
Run the program and enter your license key.
License locks to your computer (one PC only).

For support, contact: https://discord.com/invite/DhEQBfBcpt

Thank you for your purchase!"""
            
            return jsonify({
                'success': True,
                'data': delivery_message
            })
        else:
            return jsonify({'success': False, 'message': 'GitHub update failed'}), 500
    
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({'status': 'ok'})
    
@app.route('/', methods=['GET'])
def index():
    """Root endpoint - keeps server warm"""
    return jsonify({
        'status': 'online',
        'service': 'TwitchChecker License Server',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/bind-hwid', methods=['POST'])
def bind_hwid():
    """Bind license to HWID"""
    try:
        data = request.json
        license_key = data.get('license_key')
        hwid = data.get('hwid')
        
        licenses, sha = get_github_file()
        
        for lic in licenses:
            if lic['key'] == license_key:
                lic['hwid'] = hwid
                break
        
        if update_github_file(licenses, sha):
            return jsonify({'success': True})
        
        return jsonify({'success': False}), 500
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/reset-hwid', methods=['POST'])
def reset_hwid():
    """Reset license HWID"""
    try:
        data = request.json
        license_key = data.get('license_key')
        admin_key = data.get('admin_key')
        
        if admin_key != 'TwitchChecker2026AdminKey_SecurePassword':
            return jsonify({'error': 'Unauthorized'}), 401
        
        licenses, sha = get_github_file()
        
        for lic in licenses:
            if lic['key'] == license_key:
                lic['hwid'] = None
                break
        
        if update_github_file(licenses, sha):
            print(f"✓ HWID reset for {license_key}")
            return jsonify({'success': True})
        
        return jsonify({'success': False}), 500
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

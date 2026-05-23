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
SELLAUTH_SECRET = os.environ.get('SELLAUTH_SECRET', '')

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
        
        # Get custom fields (Sellauth sends them as a dict or list)
        custom_fields = data.get('custom_fields', {})
        
        # Extract customer email - try multiple possible locations
        customer_email = (
            custom_fields.get('Email Address') or
            custom_fields.get('email_address') or
            custom_fields.get('email') or
            data.get('customer_email') or
            data.get('email') or
            data.get('buyer_email') or
            'no-email-provided'
        )
        
        customer_name = data.get('customer_name') or data.get('buyer_name') or customer_email.split('@')[0]
        
        # Determine license duration based on variant
        variant_title = str(data.get('variant_title', '')).lower()
        product_title = str(data.get('product_title', '')).lower()

        if 'lifetime' in variant_title or 'lifetime' in product_title:
            duration_days = 0
        elif '30 days' in variant_title or '30 day' in variant_title:
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
            
            return jsonify({
                'success': True,
                'license_key': new_license['key'],
                'message': f'Your license key: {new_license["key"]}'
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to update GitHub'}), 500
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})

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
            return jsonify({
                'success': True,
                'license_key': new_license['key']
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

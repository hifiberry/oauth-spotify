from flask import Flask, redirect, request, jsonify, render_template_string, abort, send_from_directory
import requests
import os
import uuid
import time
import functools
from collections import defaultdict
import pathlib

app = Flask(__name__)

# Configuration from environment variables
CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = os.environ.get('REDIRECT_URI')
PORT = int(os.environ.get('PORT', 4180))
PROXY_SECRET = os.environ.get('PROXY_SECRET', '')  # Secret for clients to authenticate with the proxy
ENABLE_DEMO = os.environ.get('ENABLE_DEMO', '').lower() in ('true', 'yes', '1')  # Enable demo page
BASE_PATH = os.environ.get('BASE_PATH', '')  # Base path when running behind reverse proxy (e.g., '/spotify')

# In-memory storage for auth tokens (in production, use Redis/DB for persistence)
auth_store = defaultdict(dict)

def require_auth(f):
    """Decorator to require authentication via proxy secret"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not PROXY_SECRET:
            # If no secret is set, authentication is disabled
            return f(*args, **kwargs)
        
        # Check for secret in header or query parameter
        client_secret = request.headers.get('X-Proxy-Secret') or request.args.get('proxy_secret')
        
        if client_secret != PROXY_SECRET:
            abort(401, description="Unauthorized: Invalid or missing proxy secret")
            
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if ENABLE_DEMO:
        # Return the contents of sample-client.html file with placeholders replaced
        try:
            # Get the directory where the script is located
            script_dir = pathlib.Path(__file__).parent.absolute()
            sample_client_path = script_dir / 'sample-client.html'
              # Determine the proxy URL from request information
            host = request.headers.get('Host', f'localhost:{PORT}')
            protocol = request.headers.get('X-Forwarded-Proto', 'http')
            
            # Use base path if configured
            if BASE_PATH:
                proxy_url = f"{protocol}://{host}{BASE_PATH}"
            else:
                proxy_url = f"{protocol}://{host}"
            
            with open(sample_client_path, 'r') as file:
                html_content = file.read()
                # Replace placeholders with actual values
                html_content = html_content.replace('{{PROXY_URL}}', proxy_url)
                html_content = html_content.replace('{{PROXY_SECRET}}', PROXY_SECRET)
                return html_content
        except Exception as e:
            app.logger.error(f"Error serving demo page: {e}")
            # Fall back to basic page if there's an error
            return f'''
            <html>
              <head><title>Spotify Auth</title></head>
              <body>
                <h1>Spotify Authentication</h1>
                <p>Demo page enabled but could not be loaded: {str(e)}</p>
                <a href="/login">Login with Spotify</a>
              </body>
            </html>
            '''
    else:
        # Return the basic page
        return '''
        <html>
          <head><title>Spotify Auth</title></head>
          <body>
            <h1>Spotify Authentication</h1>
            <a href="/login">Login with Spotify</a>
          </body>
        </html>
        '''

@app.route('/create_session', methods=['GET'])
@require_auth
def create_session():
    """Creates a new auth session and returns session ID"""
    session_id = str(uuid.uuid4())
    auth_store[session_id] = {
        'created': time.time(),
        'status': 'pending',
    }
    return jsonify({'session_id': session_id})

@app.route('/login/<session_id>')
@require_auth
def login_with_session(session_id):
    """Initiates Spotify login with a session ID"""
    if session_id not in auth_store:
        return "Invalid session ID", 400
        
    scopes = 'user-read-private user-read-email'
    auth_url = 'https://accounts.spotify.com/authorize'
    params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'scope': scopes,
        'redirect_uri': REDIRECT_URI,
        'state': session_id  # Pass session ID as state parameter
    }
    
    url = f"{auth_url}?" + "&".join([f"{key}={val}" for key, val in params.items()])
    return redirect(url)

@app.route('/login')
def login():
    """Legacy login route without session"""
    session_id = str(uuid.uuid4())
    auth_store[session_id] = {
        'created': time.time(),
        'status': 'pending',
    }
    return redirect(f'/login/{session_id}')

@app.route('/callback')
def callback():
    code = request.args.get('code')
    session_id = request.args.get('state')
    
    if not code or not session_id:
        return "Error: Missing authorization code or session ID", 400
    
    if session_id not in auth_store:
        return "Error: Invalid session ID", 400
    
    # Exchange code for access token
    token_url = 'https://accounts.spotify.com/api/token'
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    response = requests.post(token_url, data=payload)
    
    if response.status_code != 200:
        auth_store[session_id]['status'] = 'error'
        auth_store[session_id]['error'] = response.text
        return f"Error getting access token: {response.text}", 500
    
    token_data = response.json()
    
    # Store token data in session
    auth_store[session_id]['status'] = 'completed'
    auth_store[session_id]['token_data'] = token_data
    auth_store[session_id]['completed_at'] = time.time()
    
    return render_template_string('''
    <html>
      <head><title>Authentication Successful</title></head>
      <body>
        <h1>Authentication Successful</h1>
        <p>You have successfully authenticated with Spotify.</p>
        <p>You can close this window now.</p>
        <p><small>Session ID: {{ session_id }}</small></p>
      </body>
    </html>
    ''', session_id=session_id)

@app.route('/poll/<session_id>', methods=['GET'])
@require_auth
def poll_session(session_id):
    """Allows clients to poll for authentication status"""
    if session_id not in auth_store:
        return jsonify({"error": "Invalid session ID"}), 404
    
    session_data = auth_store[session_id]
    
    response = {
        "status": session_data['status']
    }
    
    if session_data['status'] == 'completed':
        response['token_data'] = session_data['token_data']
    elif session_data['status'] == 'error':
        response['error'] = session_data.get('error', 'Unknown error')
    
    return jsonify(response)

@app.route('/refresh', methods=['POST'])
@require_auth
def refresh_token():
    refresh_token = request.json.get('refresh_token')
    
    if not refresh_token:
        return jsonify({"error": "Refresh token is required"}), 400
    
    token_url = 'https://accounts.spotify.com/api/token'
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    response = requests.post(token_url, data=payload)
    
    if response.status_code != 200:
        return jsonify({"error": f"Error refreshing token: {response.text}"}), 500
    
    return jsonify(response.json())

# Clean up expired sessions periodically
@app.before_request
def cleanup_sessions():
    current_time = time.time()
    expired_sessions = []
    for session_id, data in auth_store.items():
        # Remove sessions older than 1 hour
        if current_time - data['created'] > 3600:
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        auth_store.pop(session_id, None)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
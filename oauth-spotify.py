from flask import Flask, redirect, request, jsonify, render_template_string, abort, send_from_directory
import requests
import os
import uuid
import time
import functools
import logging
import json
from collections import defaultdict
import pathlib
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = Flask(__name__)

# Configuration from environment variables
CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = os.environ.get('REDIRECT_URI')
PORT = int(os.environ.get('PORT', 4180))
PROXY_SECRET = os.environ.get('PROXY_SECRET', '')  # Secret for clients to authenticate with the proxy
ENABLE_DEMO = os.environ.get('ENABLE_DEMO', '').lower() in ('true', 'yes', '1')  # Enable demo page
BASE_PATH = os.environ.get('BASE_PATH', '')  # Base path when running behind reverse proxy (e.g., '/spotify')

# Create a simple in-memory storage for auth sessions
# Since we're using only one worker, this is safe
auth_store = {}

# Session functions are no longer needed since we're using simple in-memory dictionary
# and a single worker

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

def get_client_credentials():
    """Get client_id and client_secret from headers if present, otherwise from environment."""
    client_id = request.headers.get('X-Spotify-Client-Id', CLIENT_ID)
    client_secret = request.headers.get('X-Spotify-Client-Secret', CLIENT_SECRET)
    return client_id, client_secret

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
    
    # Allow storing the initial scope with the session
    default_scopes = 'user-read-private user-read-email'
    scope = request.args.get('scope', default_scopes)
    
    auth_store[session_id] = {
        'created': time.time(),
        'status': 'pending',
        'scope': scope
    }
    app.logger.info(f"Created new session: {session_id}")
    return jsonify({'session_id': session_id})

@app.route('/login/<session_id>')
@require_auth
def login_with_session(session_id):
    """Initiates Spotify login with a session ID"""
    app.logger.info(f"Login attempt with session ID: {session_id}")
    app.logger.info(f"Auth store has {len(auth_store)} sessions")
    
    if session_id not in auth_store:
        error_msg = f"Invalid session ID: {session_id}"
        app.logger.error(error_msg)
        return error_msg, 400
        
    app.logger.info(f"Session found, redirecting to Spotify auth")
    
    # Allow client to specify the scope
    default_scopes = 'user-read-private user-read-email'
    scopes = request.args.get('scope', default_scopes)
    app.logger.info(f"Requested scopes for session {session_id}: {scopes}")
    # Store the scope in the session for reference
    auth_store[session_id]['scope'] = scopes
    
    auth_url = 'https://accounts.spotify.com/authorize'
    # Use dynamic client_id
    client_id, client_secret = get_client_credentials()
    app.logger.info(f"Storing client_id for session {session_id}: {client_id}")
    # Store the client credentials in the session
    auth_store[session_id]['client_id'] = client_id
    auth_store[session_id]['client_secret'] = client_secret
    params = {
        'response_type': 'code',
        'client_id': client_id,
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
    app.logger.info(f"Created new session via legacy login: {session_id}")
    
    # Preserve scope if provided in query params
    scope_param = ''
    if request.args.get('scope'):
        scope_param = f"?scope={request.args.get('scope')}"

        
    
    return redirect(f'/login/{session_id}{scope_param}')

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
    # Use client_id and client_secret from session if present
    session_data = auth_store[session_id]
    client_id = session_data.get('client_id', CLIENT_ID)
    client_secret = session_data.get('client_secret', CLIENT_SECRET)
    app.logger.info(f"Using client_id for callback session {session_id}: {client_id}")
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': client_id,
        'client_secret': client_secret
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(token_url, data=payload, headers=headers)
    
    if response.status_code != 200:
        auth_store[session_id]['status'] = 'error'
        auth_store[session_id]['error'] = response.text
        return f"Error getting access token: {response.text}", 500
    
    token_data = response.json()
    # Store token data in session
    auth_store[session_id]['status'] = 'completed'
    auth_store[session_id]['token_data'] = token_data
    auth_store[session_id]['completed_at'] = time.time()
    app.logger.info(f"Authentication completed for session: {session_id}")
    
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
    session_id = request.json.get('session_id')
    if session_id and session_id in auth_store:
        session_data = auth_store[session_id]
        client_id = session_data.get('client_id', CLIENT_ID)
        client_secret = session_data.get('client_secret', CLIENT_SECRET)
        app.logger.info(f"Using stored client_id for refresh session {session_id}: {client_id}")
    else:
        client_id, client_secret = get_client_credentials()
        app.logger.info(f"Using fallback client_id for refresh: {client_id} (no session_id or not found)")
    token_url = 'https://accounts.spotify.com/api/token'
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(token_url, data=payload, headers=headers)
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
        if current_time - data.get('created', 0) > 3600:
            expired_sessions.append(session_id)
    
    if expired_sessions:
        for session_id in expired_sessions:
            auth_store.pop(session_id, None)
        app.logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
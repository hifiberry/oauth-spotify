# Spotify OAuth Proxy - Authentication & API Usage

This document provides detailed information about authenticating with and using the Spotify OAuth Proxy API.

## Authentication

All protected endpoints require authentication with a proxy secret. This secret acts as an API key to prevent unauthorized access to your Spotify OAuth service.

### Authentication Methods

There are two ways to authenticate API requests:

1. **HTTP Header (recommended)**: Add the `X-Proxy-Secret` header to your HTTP requests
   ```
   X-Proxy-Secret: your_proxy_secret
   ```

2. **Query Parameter**: Append the `proxy_secret` parameter to the request URL
   ```
   ?proxy_secret=your_proxy_secret
   ```

### Protected Endpoints

The following API endpoints require authentication:
- `/create_session`
- `/login/<session_id>`
- `/poll/<session_id>`
- `/refresh`

## API Reference

### Creating a Session

Creates a new OAuth session that can be used for the Spotify authentication flow.

**Endpoint:** `GET /create_session`
**Authentication:** Required
**Response Format:** JSON

**Example Request:**
```http
GET /create_session HTTP/1.1
Host: example.com
X-Proxy-Secret: your_proxy_secret
```

**Example Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Initiating Login

Redirects the user to Spotify's authorization page to begin the OAuth flow.

**Endpoint:** `GET /login/<session_id>`
**Authentication:** Required
**Response:** Redirect to Spotify

**Example Request:**
```http
GET /login/550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Host: example.com
X-Proxy-Secret: your_proxy_secret
```

**Result:** User is redirected to Spotify's login page

### Legacy Login (Without Session ID)

Creates a new session internally and redirects to the login flow.

**Endpoint:** `GET /login`
**Authentication:** Not Required
**Response:** Redirect to Spotify

**Example Request:**
```http
GET /login HTTP/1.1
Host: example.com
```

**Result:** A session ID is generated automatically and user is redirected to Spotify's login page

### OAuth Callback

This endpoint receives the OAuth code from Spotify after user authorization. Users should not call this endpoint directly - it's used by Spotify's OAuth service to return the authorization code.

**Endpoint:** `GET /callback`
**Authentication:** Not Required
**Parameters:**
  - `code`: OAuth authorization code (provided by Spotify)
  - `state`: Session ID (provided by Spotify, set originally in the login request)

### Polling Session Status

Check the status of an authentication session. Use this to determine when a user has completed authentication and to retrieve tokens.

**Endpoint:** `GET /poll/<session_id>`
**Authentication:** Required
**Response Format:** JSON

**Example Request:**
```http
GET /poll/550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Host: example.com
X-Proxy-Secret: your_proxy_secret
```

**Example Response (Pending):**
```json
{
  "status": "pending"
}
```

**Example Response (Completed):**
```json
{
  "status": "completed",
  "token_data": {
    "access_token": "NgCXRK...MzYjw",
    "token_type": "Bearer",
    "expires_in": 3600,
    "refresh_token": "NgAagA...Um_SHo",
    "scope": "user-read-private user-read-email"
  }
}
```

**Example Response (Error):**
```json
{
  "status": "error",
  "error": "Error details here"
}
```

### Refreshing Tokens

Refresh an expired access token using a refresh token.

**Endpoint:** `POST /refresh`
**Authentication:** Required
**Request Format:** JSON
**Response Format:** JSON

**Example Request:**
```http
POST /refresh HTTP/1.1
Host: example.com
X-Proxy-Secret: your_proxy_secret
Content-Type: application/json

{
  "refresh_token": "NgAagA...Um_SHo"
}
```

**Example Response:**
```json
{
  "access_token": "NgCXRKdjsf...MzYjw",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "user-read-private user-read-email"
}
```

## OAuth Flow Implementation

### Complete OAuth Flow

1. **Create a session:**
   - Make a GET request to `/create_session`
   - Store the returned `session_id`

2. **Initiate authentication:**
   - Redirect user to `/login/<session_id>` (requires authentication)
   - Spotify will process the login and redirect back to your callback URL

3. **Poll for status:**
   - Actively poll `/poll/<session_id>` every 2 seconds until `status` is `completed` or `error`
   - When completed, retrieve and store the tokens from the response
   - Close the authentication popup window if it's still open

4. **Using tokens:**
   - Use the `access_token` for Spotify API requests
   - When the token expires, use the `refresh_token` to get a new one via `/refresh`

### Active Polling and UX Considerations

For the best user experience:

1. **Regular Polling:** Poll the `/poll/<session_id>` endpoint every 2 seconds to quickly detect when authentication has completed.

2. **Handle Authentication Window:** When authentication completes, automatically close the popup window that was opened for the Spotify login.

3. **Timeout Handling:** Implement a timeout for the polling (e.g., stop after 5 minutes) to prevent indefinite polling if the user abandons the flow.

4. **Visual Feedback:** Show a loading indicator or progress message while waiting for authentication to complete.

## Demo Client

A sample HTML client is included in the repository (`sample-client.html`) that demonstrates the complete OAuth flow. When the proxy's `ENABLE_DEMO` environment variable is set to `true`, this client is served at the root URL.

### Sample Code (JavaScript)

```javascript
// Create a session
async function createSession() {
  const response = await fetch('https://example.com/create_session', {
    headers: {
      'X-Proxy-Secret': 'your_proxy_secret'
    }
  });
  const data = await response.json();
  return data.session_id;
}

// Poll for authentication status
async function pollStatus(sessionId) {
  const response = await fetch(`https://example.com/poll/${sessionId}`, {
    headers: {
      'X-Proxy-Secret': 'your_proxy_secret'
    }
  });
  return await response.json();
}

// Refresh an access token
async function refreshToken(refreshToken) {
  const response = await fetch('https://example.com/refresh', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Proxy-Secret': 'your_proxy_secret'
    },
    body: JSON.stringify({ refresh_token: refreshToken })
  });
  return await response.json();
}

// Example implementation with active polling every 2 seconds
function startAuthFlow() {
  let pollInterval;
  let authWindow;
  
  // Create a session and open the auth window
  createSession().then(sessionId => {
    // Store the session ID
    const sessionId = data.session_id;
    
    // Open the authentication popup
    const loginUrl = `https://example.com/login/${sessionId}?proxy_secret=your_proxy_secret`;
    authWindow = window.open(loginUrl, 'SpotifyLogin', 'width=800,height=600');
    
    // Start polling every 2 seconds
    pollInterval = setInterval(() => {
      pollStatus(sessionId).then(status => {
        // Check if authentication is completed
        if (status.status === 'completed') {
          // Authentication successful
          console.log('Authentication completed!', status.token_data);
          
          // Save the tokens
          const tokens = status.token_data;
          
          // Stop polling
          clearInterval(pollInterval);
          
          // Close the authentication window if still open
          if (authWindow && !authWindow.closed) {
            authWindow.close();
          }
          
          // Continue with your application logic
          handleSuccessfulAuth(tokens);
        } 
        else if (status.status === 'error') {
          // Authentication failed
          console.error('Authentication error:', status.error);
          clearInterval(pollInterval);
          
          if (authWindow && !authWindow.closed) {
            authWindow.close();
          }
        }
        // If status is 'pending', continue polling
      }).catch(error => {
        console.error('Error polling auth status:', error);
        clearInterval(pollInterval);
      });
    }, 2000); // Poll every 2 seconds
  }).catch(error => {
    console.error('Error creating session:', error);
  });
}
```

## Security Notes

1. Always keep your `PROXY_SECRET` confidential
2. Use HTTPS for all API communications
3. Store tokens securely and never expose them to client-side code
4. The service automatically cleans up expired sessions that are older than 1 hour

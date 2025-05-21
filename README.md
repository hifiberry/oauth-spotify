# Spotify OAuth Proxy

A simple Flask application that handles OAuth authentication with Spotify.

The application uses Gunicorn, a production-ready WSGI server, instead of Flask's built-in development server. For simplicity and session persistence, a single worker is used to avoid data sharing complexities.

## Docker Setup

### Build and Run with Docker

```bash
docker build -t spotify-oauth-proxy .
docker run -p 4180:4180 \
  -e SPOTIFY_CLIENT_ID=your_spotify_client_id \
  -e SPOTIFY_CLIENT_SECRET=your_spotify_client_secret \
  -e REDIRECT_URI=your_redirect_uri \
  -e PROXY_SECRET=your_proxy_secret \
  spotify-oauth-proxy
```

Replace `your_spotify_client_id`, `your_spotify_client_secret`, `your_redirect_uri`, and `your_proxy_secret` with your actual credentials.

To enable the built-in demo page:

```bash
docker run -p 4180:4180 \
  -e SPOTIFY_CLIENT_ID=your_spotify_client_id \
  -e SPOTIFY_CLIENT_SECRET=your_spotify_client_secret \
  -e REDIRECT_URI=your_redirect_uri \
  -e PROXY_SECRET=your_proxy_secret \
  -e ENABLE_DEMO=true \
  spotify-oauth-proxy
```

### Run with Docker Compose

```bash
# First, edit docker-compose.yml to add your Spotify API credentials
docker-compose up -d
```

This will start the OAuth proxy with Nginx as a reverse proxy. The docker-compose.yml file has ENABLE_DEMO=true by default, so you can access the demo at http://localhost/spotify/ path.

#### Using Nginx as a Reverse Proxy

The docker-compose.yml is set up to use Nginx as a reverse proxy in front of the OAuth service. This offers several benefits:

1. Better security (the OAuth service isn't directly exposed)
2. Ability to handle SSL termination
3. Ability to serve multiple applications behind the same domain

The Spotify OAuth proxy is accessible at http://localhost/spotify/ (through Nginx) rather than directly at port 4180. Nginx forwards all requests to the OAuth service automatically.

**Note:** The root URL (http://localhost/) will redirect to http://localhost/spotify/ for convenience.

## Environment Variables

- `SPOTIFY_CLIENT_ID`: Your Spotify application client ID
- `SPOTIFY_CLIENT_SECRET`: Your Spotify application client secret
- `REDIRECT_URI`: The URI that Spotify will redirect to after authentication
- `PORT`: The port the application will run on (default: 4180)
- `PROXY_SECRET`: Secret key for clients to authenticate with the proxy (if empty, authentication is disabled)
- `ENABLE_DEMO`: When set to "true", the server will serve the demo HTML page at the root URL (default: false). The demo page will be automatically configured with the correct proxy URL and secret.
- `BASE_PATH`: Base path when running behind a reverse proxy (e.g., '/spotify'). This helps the application generate proper URLs when served from a subpath.
- `REDIS_URL`: Redis connection URL for session storage (default: redis://redis:6379/0)

## Client Authentication

Clients using this proxy must include the proxy secret in their requests to protected endpoints. This can be done in one of two ways:

1. Using an HTTP header: `X-Proxy-Secret: your_proxy_secret`
2. Using a query parameter: `?proxy_secret=your_proxy_secret`

### Protected Endpoints

The following endpoints require authentication:
- `/create_session`
- `/login/<session_id>`
- `/poll/<session_id>`
- `/refresh`

## Sample Client Usage

A sample client HTML file is provided to demonstrate how to use the proxy:

1. Start the OAuth proxy service
2. Open the `sample-client.html` file in a browser or access it via http://localhost:8080 if using Docker Compose
3. Enter the proxy URL (default: http://localhost:4180)
4. Enter the proxy secret if you configured one
5. Click "Start Authentication" to begin the Spotify OAuth flow
6. A popup window will open for Spotify login
7. After successful authentication, you can check the status and retrieve tokens
8. You can also test token refresh

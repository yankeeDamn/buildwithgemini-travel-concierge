import requests
import google.auth
import google.auth.transport.requests

credentials, project = google.auth.default()
request = google.auth.transport.requests.Request()
credentials.refresh(request)

url = "https://developerknowledge.googleapis.com/mcp/message"
# Wait, MCP over SSE requires first connecting to the SSE endpoint to get a session, then posting to the message endpoint.

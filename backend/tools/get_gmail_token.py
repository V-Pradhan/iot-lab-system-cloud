"""One-time helper: gives the system permission to send e-mail from ONE Gmail account.

Run it on your own PC (not on the server), sign in with the Gmail account that should send the
e-mails (your own now, the teacher's later), and copy the 4 values it prints into the server's
environment variables.

    python tools/get_gmail_token.py CLIENT_ID CLIENT_SECRET

CLIENT_ID and CLIENT_SECRET come from Google Cloud Console (see README, "Gmail sending").
"""
import http.server
import sys
import threading
import urllib.parse
import webbrowser

import httpx

PORT = 8765
REDIRECT = f"http://localhost:{PORT}"
SCOPE = "https://www.googleapis.com/auth/gmail.send"


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    client_id, client_secret = sys.argv[1], sys.argv[2]
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result["code"] = (q.get("code") or [""])[0]
            result["error"] = (q.get("error") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>Done. You can close this tab and return to the terminal.</h2>")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, *a):
            pass

    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent"})
    print("Opening the browser. Sign in with the Gmail account that will SEND the e-mails.")
    print("If it does not open, paste this link into a browser:\n" + url + "\n")
    webbrowser.open(url)
    server = http.server.HTTPServer(("localhost", PORT), Handler)
    server.serve_forever()

    if not result.get("code"):
        sys.exit("No permission was given: " + (result.get("error") or "unknown error"))
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": result["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"}, timeout=30)
    data = r.json()
    if "refresh_token" not in data:
        sys.exit(f"Google did not return a refresh token: {data}")
    who = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile",
                    headers={"Authorization": "Bearer " + data["access_token"]}, timeout=30)
    sender = who.json().get("emailAddress", "") if who.status_code == 200 else ""
    print("\nAdd these to the server's environment variables:\n")
    print("EMAIL_PROVIDER=gmail_api")
    print(f"GMAIL_CLIENT_ID={client_id}")
    print(f"GMAIL_CLIENT_SECRET={client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={data['refresh_token']}")
    print(f"GMAIL_SENDER={sender or 'your.gmail.address@gmail.com'}")


if __name__ == "__main__":
    main()

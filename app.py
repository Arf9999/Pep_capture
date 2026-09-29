"""
Web Dashboard Server for PEP Social Accounts
Lightweight REST API & Static UI Server using Python's standard library.
"""

import os
import json
import functools
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from db import (
    init_database, 
    query_person_by_id, 
    search_peps, 
    get_summary_stats, 
    update_account_verification,
    revert_verification,
    get_audit_history
)

PORT = 9090
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class DashboardHandler(SimpleHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API: Verify account (with verifier attribution and audit ledger)
        if path == "/api/verify":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body.decode("utf-8"))

                account_id = data.get("account_id")
                person_id = data.get("person_id")
                profile_url = data.get("profile_url")
                status = data.get("status", "verified")
                verifier_id = data.get("verifier_id", "remote_verifier")
                notes = data.get("notes", "")

                result = update_account_verification(
                    account_id=account_id,
                    person_id=person_id,
                    profile_url=profile_url,
                    status=status,
                    verifier_id=verifier_id,
                    notes=notes
                )
                if result.get("success"):
                    stats = get_summary_stats()
                    self._send_json({"success": True, "result": result, "stats": stats})
                else:
                    self._send_json(result, status=404)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        # API: 1-Click Revert previous verification
        if path == "/api/revert":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body.decode("utf-8"))

                log_id = data.get("log_id")
                verifier_id = data.get("verifier_id", "remote_verifier")
                reason = data.get("reason", "")

                if not log_id:
                    self._send_json({"error": "log_id is required"}, status=400)
                    return

                result = revert_verification(log_id=int(log_id), verifier_id=verifier_id, reason=reason)
                if result.get("success"):
                    stats = get_summary_stats()
                    self._send_json({"success": True, "result": result, "stats": stats})
                else:
                    self._send_json(result, status=404)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        # API: Summary Stats
        if path == "/api/stats":
            stats = get_summary_stats()
            self._send_json(stats)
            return

        # API: Global Audit History
        if path == "/api/audit":
            limit = int(query_params.get("limit", [50])[0])
            history = get_audit_history(limit=limit)
            self._send_json(history)
            return

        # API: Candidate Audit History
        if path.startswith("/api/audit/"):
            pers_id = path.split("/api/audit/")[1].strip()
            history = get_audit_history(person_id=pers_id)
            self._send_json(history)
            return

        # API: Search Candidates
        if path == "/api/candidates":
            q = query_params.get("q", [""])[0]
            platform = query_params.get("platform", [""])[0]
            confidence = query_params.get("confidence", [""])[0]
            verification = query_params.get("verification", [""])[0]
            limit = int(query_params.get("limit", [50])[0])
            offset = int(query_params.get("offset", [0])[0])

            results = search_peps(
                query_text=q,
                platform_filter=platform,
                confidence_filter=confidence,
                verification_filter=verification,
                limit=limit,
                offset=offset
            )
            self._send_json(results)
            return

        # API: Get Candidate by pers_xxx ID
        if path.startswith("/api/candidates/"):
            pers_id = path.split("/api/candidates/")[1].strip()
            person = query_person_by_id(pers_id)
            if person:
                self._send_json(person)
            else:
                self._send_json({"error": f"Person '{pers_id}' not found"}, status=404)
            return

        # Serve methodology explainer page
        if path == "/methodology" or path == "/methodology.html":
            meth_file = os.path.join(os.path.dirname(__file__), "docs", "methodology.html")
            if os.path.exists(meth_file):
                with open(meth_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # Serve index.html for root path
        if path == "/" or path == "/index.html":
            self.path = "/index.html"

        super().do_GET()


def run_dashboard(port: int = PORT):
    init_database()
    os.makedirs(STATIC_DIR, exist_ok=True)
    handler_class = functools.partial(DashboardHandler, directory=STATIC_DIR)
    # Listen on 0.0.0.0 for LAN, VPN, Tailscale, or ngrok remote verifier access
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, handler_class)
    print(f"PEP Social Intelligence Dashboard running at http://0.0.0.0:{port}")
    print(f"Accessible locally at http://localhost:{port} and to remote verifiers via tunnel/LAN IP.")
    httpd.serve_forever()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run_dashboard(port)


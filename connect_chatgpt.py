"""Authorize the hosted Serra instance with the official ChatGPT OSS OAuth flow.

Run locally on the same computer as the browser. The output bundle is encrypted
with a passphrase and is intended to be uploaded to the protected app over HTTPS.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import json
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

ROOT = Path(__file__).resolve().parent
CALLBACK = "http://127.0.0.1:1455/auth/callback"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
RESULT: dict[str, str] = {}
DONE = threading.Event()


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_error(404)
            return
        RESULT.update({k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items() if v})
        body = "Autorización recibida. Puedes volver a la ventana de PowerShell y cerrarla."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())
        DONE.set()

    def log_message(self, *_args):
        return


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def main() -> int:
    host_file = ROOT / "data" / "app" / "chatgpt_remote_host_id.txt"
    registration_file = ROOT / "data" / "app" / "chatgpt_registration.json"
    host_file.parent.mkdir(parents=True, exist_ok=True)
    if host_file.exists():
        host_id = host_file.read_text(encoding="utf-8").strip()
    else:
        host_id = "urn:uuid:" + str(uuid4())
        host_file.write_text(host_id, encoding="utf-8")

    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    existing = {}
    if registration_file.exists():
        try:
            existing = json.loads(registration_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
    requested_client_id = str(existing.get("client_id") or "dynamic_agent_client")
    params = {
        "client_id": requested_client_id,
        "ext_agent_host_id": host_id, "response_type": "code", "redirect_uri": CALLBACK,
        "scope": SCOPES, "resource": RESOURCE, "state": state, "nonce": nonce,
        "code_challenge_method": "S256", "code_challenge": challenge,
    }
    if requested_client_id == "dynamic_agent_client":
        params["agent_name_hint"] = "Serra Training"
    try:
        server = HTTPServer(("127.0.0.1", 1455), CallbackHandler)
    except OSError:
        print("No se puede usar el puerto local 1455. Cierra la app que lo ocupa e inténtalo de nuevo.")
        return 1
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "https://auth.openai.com/api/accounts/authorize?" + urllib.parse.urlencode(params)
    print("Se abrirá OpenAI en tu navegador. Inicia sesión y acepta los permisos para esta app.")
    webbrowser.open(url)
    try:
        if not DONE.wait(300):
            print("La autorización no terminó en cinco minutos.")
            return 1
    finally:
        server.shutdown()
        server.server_close()
    if RESULT.get("state") != state or RESULT.get("error"):
        print("No se pudo validar la respuesta de autorización.")
        return 1
    code = RESULT.get("code", "")
    callback_client_id = RESULT.get("client_id", "")
    if requested_client_id == "dynamic_agent_client":
        client_id = callback_client_id
    else:
        client_id = requested_client_id
        if callback_client_id and callback_client_id != requested_client_id:
            print("OpenAI devolvió otro registro; se rechazó para proteger la cuenta elegida.")
            return 1
    if not code or not client_id or client_id == "dynamic_agent_client":
        print("OpenAI no devolvió el registro de app esperado. No se han guardado credenciales.")
        return 1

    form = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code, "client_id": client_id,
        "code_verifier": verifier, "redirect_uri": CALLBACK, "resource": RESOURCE,
    }).encode()
    req = urllib.request.Request("https://auth.openai.com/api/accounts/oauth/token", data=form,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            token = json.loads(response.read())
    except Exception:
        print("OpenAI no pudo completar el intercambio. Vuelve a iniciar la autorización.")
        return 1
    granted = str(token.get("scope", "")).split()
    if "chatgpt.tokens.use.direct" not in granted:
        print("No se concedió el permiso para usar el plan ChatGPT en la app.")
        return 1
    try:
        jwks = jwt.PyJWKClient("https://auth.openai.com/.well-known/jwks.json", timeout=15)
        signing_key = jwks.get_signing_key_from_jwt(token["id_token"]).key
        algorithm = jwt.get_unverified_header(token["id_token"]).get("alg")
        if algorithm not in ("RS256", "PS256", "ES256", "EdDSA"):
            raise ValueError("Unsupported ID token signature algorithm")
        claims = jwt.decode(token["id_token"], signing_key, algorithms=[algorithm],
                            audience=client_id, issuer="https://auth.openai.com",
                            options={"require": ["sub", "iat", "exp"]}, leeway=5)
    except Exception:
        print("No se pudo validar la identidad firmada por OpenAI. No se han guardado credenciales.")
        return 1
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        print("La respuesta de OpenAI no coincide con esta autorización.")
        return 1

    credentials = {
        "client_id": client_id, "access_token": token.get("access_token"),
        "refresh_token": token.get("refresh_token"), "id_token": token.get("id_token"),
        "oauth_nonce": nonce, "scopes": granted, "expires_in": token.get("expires_in", 3600),
        "token_type": token.get("token_type", "Bearer"), "ext_agent_host_id": host_id,
        "subject": claims["sub"], "email": claims.get("email"),
    }
    password = getpass.getpass("Crea una contraseña de transferencia (mínimo 12 caracteres): ")
    confirm = getpass.getpass("Repítela para confirmar: ")
    if len(password) < 12 or not secrets.compare_digest(password, confirm):
        print("Contraseña demasiado corta o las contraseñas no coinciden; no se ha creado el archivo.")
        return 1
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(password.encode())
    ciphertext = AESGCM(key).encrypt(iv, json.dumps(credentials, separators=(",", ":")).encode(),
                                    b"Serra ChatGPT credential transfer v1")
    bundle = {"version": 1, "salt": b64url(salt), "nonce": b64url(iv), "ciphertext": b64url(ciphertext)}
    output = ROOT / "outputs" / "serra-chatgpt-credentials.enc"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(bundle, separators=(",", ":")), encoding="utf-8")
    registration_file.write_text(json.dumps({"client_id": client_id}, separators=(",", ":")), encoding="utf-8")
    print(f"Archivo protegido creado: {output}")
    print("Impórtalo en Conexiones dentro de la app alojada y elimina el archivo después.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""
Servidor de desarrollo para Show Sync PWA.

Modos:
  python3 serve.py                → HTTP  en :8080 (produccion)
  python3 serve.py --dev          → HTTP  en :8080 (sin cache)
  python3 serve.py --https        → HTTPS en :8443 (genera cert al arrancar)
  python3 serve.py --https --dev  → HTTPS en :8443 sin cache

Para iOS con HTTPS:
  1. Abrir https://<ip>:8443/cert.pem en Safari del iPhone
  2. "Permitir" → Settings → General → VPN & Device Management → instalar perfil
  3. Settings → General → Acerca → Ajustes de confianza del certificado → activar
  4. Listo: Service Worker funciona y se puede instalar como PWA
"""
import http.server
import socketserver
import sys
import socket
import ssl
import subprocess
import os
import tempfile

args  = [a for a in sys.argv[1:] if not a.startswith('-')]
flags = [a for a in sys.argv[1:] if a.startswith('-')]

HTTPS_MODE = '--https' in flags
DEV_MODE   = '--dev'   in flags

DEFAULT_PORT = 8443 if HTTPS_MODE else 8080
PORT = int(args[0]) if args else DEFAULT_PORT

CERT_FILE = os.path.join(os.path.dirname(__file__), 'cert.pem')
KEY_FILE  = os.path.join(os.path.dirname(__file__), 'key.pem')

MIME_OVERRIDES = {
    '.js':          'application/javascript',
    '.mjs':         'application/javascript',
    '.json':        'application/json',
    '.css':         'text/css',
    '.html':        'text/html; charset=utf-8',
    '.svg':         'image/svg+xml',
    '.webmanifest': 'application/manifest+json',
    '.pem':         'application/x-pem-file',
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        for ext, mime in MIME_OVERRIDES.items():
            if str(path).endswith(ext):
                return mime
        return super().guess_type(path)

    def end_headers(self):
        if DEV_MODE:
            self.send_header('Cache-Control', 'no-store')
        else:
            self.send_header('Cache-Control', 'max-age=86400')
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f'  {self.address_string()}  {fmt % args}')


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def generate_cert(ip):
    """Genera certificado autofirmado con SAN para que iOS lo acepte."""
    print(f'  Generando certificado SSL para IP {ip}...')

    # Config con Subject Alternative Names requeridas por iOS 13+
    cfg = f"""[req]
default_bits       = 2048
prompt             = no
default_md         = sha256
x509_extensions    = v3_req
distinguished_name = dn

[dn]
CN = {ip}

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE

[alt_names]
IP.1  = {ip}
IP.2  = 127.0.0.1
DNS.1 = localhost
"""
    with tempfile.NamedTemporaryFile('w', suffix='.cnf', delete=False) as f:
        f.write(cfg)
        cfg_path = f.name

    try:
        subprocess.run(
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
             '-keyout', KEY_FILE, '-out', CERT_FILE,
             '-days', '365', '-nodes', '-config', cfg_path],
            check=True, capture_output=True
        )
        print(f'  Certificado generado: cert.pem + key.pem (valido 365 dias)')
    except subprocess.CalledProcessError as e:
        print(f'  ERROR generando certificado: {e.stderr.decode()}')
        sys.exit(1)
    finally:
        os.unlink(cfg_path)


socketserver.TCPServer.allow_reuse_address = True

ip = get_local_ip()
mode_label = ('DEV ' if DEV_MODE else '') + ('HTTPS' if HTTPS_MODE else 'HTTP')

if HTTPS_MODE:
    if not os.path.exists(CERT_FILE) or not os.path.exists(KEY_FILE):
        generate_cert(ip)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT_FILE, KEY_FILE)

    with socketserver.TCPServer(('', PORT), Handler) as httpd:
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        print(f'\n  Show Sync [{mode_label}]')
        print(f'  → local:  https://localhost:{PORT}')
        print(f'  → movil:  https://{ip}:{PORT}')
        print(f'\n  Para instalar el certificado en iPhone:')
        print(f'  1. Safari → https://{ip}:{PORT}/cert.pem → "Permitir"')
        print(f'  2. Settings → General → VPN & Device Management → instalar')
        print(f'  3. Settings → General → Acerca → Ajustes confianza → activar')
        print(f'\n  Ctrl+C para detener\n')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n  Servidor detenido.')
else:
    with socketserver.TCPServer(('', PORT), Handler) as httpd:
        print(f'\n  Show Sync [{mode_label}]')
        print(f'  → local:  http://localhost:{PORT}')
        print(f'  → movil:  http://{ip}:{PORT}')
        print(f'\n  Ctrl+C para detener\n')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n  Servidor detenido.')

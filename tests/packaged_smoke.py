"""End-to-end HTTPS probe using the actual frozen EXE and disposable data only."""
import http.cookiejar
import ipaddress
import json
import logging
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID



def main():
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from server.app import initialize
    exe = root / 'dist/QRPointServer/QRPointServer.exe'
    with tempfile.TemporaryDirectory(prefix='qrpoint-https-test-') as temporary:
        data = Path(temporary)
        initialize(data, 'smoke-admin', 'Smoke-Test-9284')
        logging.shutdown()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'QRPoint disposable TLS test')])
        timestamp = datetime.now(timezone.utc)
        certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                       .public_key(key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(timestamp - timedelta(minutes=1)).not_valid_after(timestamp + timedelta(days=1))
                       .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                       .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
                       .sign(key, hashes.SHA256()))
        cert = data / 'test-cert.pem'
        private = data / 'test-key.pem'
        cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        with socket.socket() as address:
            address.bind(('127.0.0.1', 0))
            port = address.getsockname()[1]
        (data / 'config.json').write_text(json.dumps({'port': port, 'tls_certfile': str(cert), 'tls_keyfile': str(private)}), encoding='utf8')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(cert))), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        log = (data / 'server.log').open('wb')
        server_env = dict(os.environ, PYTHONIOENCODING='ascii')
        server = subprocess.Popen([str(exe), 'serve', '--data-dir', str(data)], stdout=log, stderr=log, env=server_env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        base = f'https://127.0.0.1:{port}/api'
        csrf = ''

        def request(path, body=None):
            data_bytes = None if body is None else json.dumps(body).encode()
            query = urllib.request.Request(base + path, data=data_bytes, headers={'Content-Type': 'application/json', 'X-CSRF-Token': csrf})
            response = opener.open(query, timeout=10)
            return json.loads(response.read()), response.headers

        try:
            for _ in range(100):
                try:
                    assert request('/health')[0]['status'] == 'ok'
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Packaged server exited during HTTPS startup')
                    time.sleep(0.1)
            else:
                raise RuntimeError('Packaged HTTPS startup timed out')
            identity, headers = request('/auth/login', {'username': 'smoke-admin', 'password': 'Smoke-Test-9284'})
            csrf = identity['csrf']
            assert 'Secure' in headers.get('Set-Cookie') and 'HttpOnly' in headers.get('Set-Cookie')
            user, _ = request('/users', {'member_code': 'SMOKE-ONLY', 'display_name': '封裝測試會員'})
            tx, _ = request('/transactions/redeem', {'idempotency_key': str(uuid.uuid4()), 'user_id': user['id'], 'amount': 100, 'reason': '封裝負點測試', 'station_id': 'TEST', 'token': user['token']})
            assert tx['balance_after'] == -100
            rows, _ = request('/transactions')
            assert rows[0]['member_name'] == user['display_name']
            member, _ = request('/portal/login', {'token': user['token']})
            assert member['balance'] == -100
            assert request('/portal/transactions')[0][0]['delta'] == -100
            print('PASS: frozen EXE, trusted-certificate HTTPS, Secure cookie, negative points, transaction names and portal')
        finally:
            shutdown = None
            try:
                if server.poll() is None:
                    shutdown = subprocess.run([str(exe), 'stop', '--data-dir', str(data)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=server_env, check=False)
                    server.wait(timeout=15)
            finally:
                log.close()
            assert server.returncode == 0, (data / 'server.log').read_text(encoding='utf8', errors='replace')
            assert shutdown is None or shutdown.returncode == 0, shutdown.stdout.decode('utf8', errors='replace')



if __name__ == '__main__':
    main()

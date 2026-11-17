import json
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from server.https_setup import configure_https

PASSWORD = 'TLS-Only-For-Test-9284'


def test_https_trusted_handshake_and_renewal(tmp_path):
    (tmp_path / 'config.json').write_text(json.dumps({'database_url': 'existing-value', 'port': 8080}), encoding='utf-8')
    result = configure_https(tmp_path, ['127.0.0.1'], ['localhost'], PASSWORD)
    config = json.loads((tmp_path / 'config.json').read_text(encoding='utf-8'))
    assert config['database_url'] == 'existing-value' and config['secure_cookie'] is True
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(config['tls_certfile'], config['tls_keyfile'])
    client_context = ssl.create_default_context(cafile=str(tmp_path / 'https/root-ca.pem'))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(5)

        def serve():
            connection, _ = listener.accept()
            with connection, server_context.wrap_socket(connection, server_side=True) as secured:
                assert secured.recv(4) == b'ping'
                secured.sendall(b'pong')

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(serve)
            with socket.create_connection(listener.getsockname(), timeout=5) as connection:
                with client_context.wrap_socket(connection, server_hostname='127.0.0.1') as secured:
                    secured.sendall(b'ping')
                    assert secured.recv(4) == b'pong'
            future.result(timeout=5)
    ca_before = (tmp_path / 'https/root-ca.pem').read_bytes()
    renewed = configure_https(tmp_path, ['127.0.0.2'], [], PASSWORD, 8443)
    assert renewed['sha256'] == result['sha256'] and renewed['port'] == 8443
    assert (tmp_path / 'https/root-ca.pem').read_bytes() == ca_before
    assert x509.load_der_x509_certificate((tmp_path / 'https/QRPoint-Root-CA.cer').read_bytes()).public_bytes(serialization.Encoding.PEM) == ca_before
    with pytest.raises((ValueError, TypeError)):
        serialization.load_pem_private_key((tmp_path / 'https/ca-private.key').read_bytes(), password=None)
    assert 'server-' in config['tls_certfile']


def test_https_invalid_input_and_password_preserve_config(tmp_path):
    for ips, names in [([], []), (['bad-ip'], [])]:
        with pytest.raises(ValueError):
            configure_https(tmp_path, ips, names, PASSWORD)
    configure_https(tmp_path, ['127.0.0.1'], [], PASSWORD)
    original = (tmp_path / 'config.json').read_bytes()
    with pytest.raises(ValueError):
        configure_https(tmp_path, ['127.0.0.1'], [], 'wrong-password')
    assert (tmp_path / 'config.json').read_bytes() == original

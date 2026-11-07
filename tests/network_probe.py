"""Live probe against a disposable running server; never changes member data."""
import argparse
import socket
import ssl
import urllib.request


def probe(host, port):
    for _ in range(3):
        try:
            with socket.create_connection((host, port), timeout=3) as connection:
                with ssl._create_unverified_context().wrap_socket(connection, server_hostname=host):
                    raise AssertionError('Test endpoint unexpectedly supports TLS')
        except (ssl.SSLError, ConnectionError):
            pass  # Expected: HTTPS cannot connect to a plain HTTP port.
    for _ in range(3):
        with socket.create_connection((host, port), timeout=3) as connection:
            connection.sendall(b'INVALID REQUEST\r\n\r\n')
            assert b'400 Bad Request' in connection.recv(4096)
    # Both invalid request classes must leave normal HTTP functioning.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://{host}:{port}/api/health', timeout=5) as result:
        assert result.status == 200
    print('PASS: 3 HTTPS attempts, 3 malformed requests, HTTP health remains 200')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18080)
    args = parser.parse_args()
    probe(args.host, args.port)

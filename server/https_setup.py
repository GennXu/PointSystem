"""Issue LAN server certificates under a password-protected private CA."""
import ipaddress
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def configure_https(data, ips, names, password, port=None):
    if len(password) < 12 or len(password.encode()) > 1023:
        raise ValueError('CA 密碼至少 12 字元，UTF-8 長度最多 1023 bytes')
    addresses = [x509.IPAddress(ipaddress.ip_address(value)) for value in ips]
    for value in names:
        name = value.encode('idna').decode('ascii').lower()
        if len(name) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in name.split('.')):
            raise ValueError('DNS 名稱格式錯誤，請勿包含網址、Port、路徑或萬用字元')
        addresses.append(x509.DNSName(name))
    if not addresses:
        raise ValueError('請指定至少一個 --ip 或 --dns')
    data = Path(data).resolve()
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('Port 必須介於 1 到 65535')
    config_path = data / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig')) if config_path.exists() else {}
    folder = data / 'https'
    folder.mkdir(parents=True, exist_ok=True)
    ca_key_path, ca_path = folder / 'ca-private.key', folder / 'root-ca.pem'
    timestamp = datetime.now(timezone.utc)
    if ca_key_path.exists() != ca_path.exists():
        raise RuntimeError('CA 檔案不完整，請從備份復原，不能自動更換信任根')
    if ca_key_path.exists():
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=password.encode())
        ca = x509.load_pem_x509_certificate(ca_path.read_bytes())
        if ca_key.public_key().public_numbers() != ca.public_key().public_numbers():
            raise RuntimeError('CA 憑證與私密金鑰不符')
        if not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise RuntimeError('現有憑證不是 CA')
        if ca.not_valid_before_utc > timestamp or ca.not_valid_after_utc <= timestamp + timedelta(days=366):
            raise RuntimeError('CA 未生效或即將到期，請規劃更換 CA 並重新設定手機信任')
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'QRPoint LAN Root CA')])
        ca = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
              .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(timestamp - timedelta(minutes=5)).not_valid_after(timestamp + timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False,
                  key_encipherment=False, data_encipherment=False, key_agreement=False,
                  key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
              .sign(ca_key, hashes.SHA256()))
        ca_key_path.write_bytes(ca_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.BestAvailableEncryption(password.encode())))
        ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    public_ca = folder / 'QRPoint-Root-CA.cer'
    public_ca.write_bytes(ca.public_bytes(serialization.Encoding.DER))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    certificate = (x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'QRPoint LAN Server')]))
        .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(timestamp - timedelta(minutes=5)).not_valid_after(timestamp + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(addresses), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
            key_encipherment=True, data_encipherment=False, key_agreement=False,
            key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256()))
    generation = uuid.uuid4().hex
    certificate_path, key_path = folder / f'server-{generation}.pem', folder / f'server-{generation}.key'
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
    config.update(tls_certfile=str(certificate_path), tls_keyfile=str(key_path), secure_cookie=True,
                  port=port if port is not None else config.get('port', 8080))
    temporary = data / ('https-config-' + generation + '.tmp')
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(config_path)
    return {'certificate': str(public_ca), 'sha256': ca.fingerprint(hashes.SHA256()).hex(),
            'expires': certificate.not_valid_after_utc.isoformat(), 'port': config['port']}

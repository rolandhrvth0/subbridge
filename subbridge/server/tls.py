"""Self-signed certificate for the optional HTTPS mode (needed by some phone browsers for wake lock)."""
from __future__ import annotations

import datetime as dt
import ipaddress
import ssl

from ..branding import APP_NAME
from ..paths import config_dir


def cert_paths():
    d = config_dir() / "tls"
    return d / "cert.pem", d / "key.pem"


def ensure_cert(ip: str) -> tuple[str, str]:
    """Create (or recreate when the LAN address changed) a 10-year self-signed certificate."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    cert_p, key_p = cert_paths()
    if cert_p.exists() and key_p.exists():
        try:
            c = x509.load_pem_x509_certificate(cert_p.read_bytes())
            ips = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)
            if ipaddress.ip_address(ip) in ips and c.not_valid_after_utc > dt.datetime.now(dt.timezone.utc):
                return str(cert_p), str(key_p)
        except Exception:  # noqa: BLE001
            pass
    cert_p.parent.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{APP_NAME} ({ip})")])
    now = dt.datetime.now(dt.timezone.utc)
    san = [x509.IPAddress(ipaddress.ip_address(ip)), x509.DNSName("localhost")]
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    key_p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
    key_p.chmod(0o600)
    cert_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(cert_p), str(key_p)


def ssl_context(ip: str) -> ssl.SSLContext:
    cert, key = ensure_cert(ip)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(cert, key)
    return ctx

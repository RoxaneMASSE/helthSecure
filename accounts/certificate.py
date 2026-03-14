# Re-use the CertificateService from the existing project
import re
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
from cryptography.x509.oid import NameOID
from datetime import datetime, timezone
from django.conf import settings
from django.core.exceptions import ValidationError


class CertificateService:

    def __init__(self):
        self.trusted_root_certs = self._load_trusted_root_cas()

    def _load_trusted_root_cas(self):
        trusted_certs = []
        trust_store_path = Path(settings.BASE_DIR) / 'trusted_cas'
        if not trust_store_path.exists():
            return trusted_certs
        for cert_file in trust_store_path.glob('*.pem'):
            try:
                with open(cert_file, 'rb') as f:
                    cert = x509.load_pem_x509_certificate(f.read(), default_backend())
                    trusted_certs.append(cert)
            except Exception as e:
                print(f"Error loading CA {cert_file}: {e}")
        return trusted_certs

    def validate_certificate_chain(self, cert_file, user_email=None, ip_address=None):
        """
        Validate a PEM certificate chain against trusted Root CAs.
        Returns dict with cert info if valid, raises ValidationError if not.
        """
        cert_data = cert_file.read()
        cert_file.seek(0)

        certs = self._parse_certificate_chain(cert_data)

        if not certs:
            raise ValidationError("No valid certificate found in the uploaded file.")

        user_cert = certs[0]

        self._verify_not_ca_certificate(user_cert)
        self._verify_certificate_dates(user_cert)
        self._verify_chain_of_trust(certs)

        return self._extract_certificate_info(user_cert)

    def _parse_certificate_chain(self, cert_data):
        certs = []
        if isinstance(cert_data, bytes):
            cert_data = cert_data.decode('utf-8')
        blocks = re.findall(
            r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',
            cert_data, re.DOTALL
        )
        for block in blocks:
            try:
                certs.append(x509.load_pem_x509_certificate(block.encode(), default_backend()))
            except Exception:
                pass
        return certs

    def _verify_not_ca_certificate(self, cert):
        try:
            bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
            if bc.value.ca:
                raise ValidationError(
                    "The uploaded certificate is a CA certificate. "
                    "Please upload your end-entity certificate (fullchain)."
                )
        except x509.ExtensionNotFound:
            pass

        if cert.subject.rfc4514_string() == cert.issuer.rfc4514_string():
            raise ValidationError(
                "The uploaded certificate is self-signed (Root CA). "
                "Please upload your fullchain: dr-test-fullchain.pem"
            )

        try:
            ku = cert.extensions.get_extension_for_class(x509.KeyUsage)
            if ku.value.key_cert_sign:
                raise ValidationError(
                    "The uploaded certificate has keyCertSign set (CA certificate). "
                    "Please upload dr-test-fullchain.pem from pki/doctors/"
                )
        except x509.ExtensionNotFound:
            pass

    def _verify_certificate_dates(self, cert):
        now = datetime.now(timezone.utc)
        try:
            not_before = cert.not_valid_before_utc
            not_after  = cert.not_valid_after_utc
        except AttributeError:
            not_before = cert.not_valid_before.replace(tzinfo=timezone.utc)
            not_after  = cert.not_valid_after.replace(tzinfo=timezone.utc)

        if not_before > now:
            raise ValidationError(f"Certificate is not yet valid (valid from {not_before}).")
        if not_after < now:
            raise ValidationError(f"Certificate has expired on {not_after}.")

    def _verify_chain_of_trust(self, certs):
        if len(certs) < 2:
            raise ValidationError(
                f"Incomplete certificate chain: {len(certs)} certificate(s) found, "
                "minimum 2 required (end-entity + intermediate/root). "
                "Please upload dr-test-fullchain.pem"
            )

        for i in range(len(certs) - 1):
            child, parent = certs[i], certs[i + 1]
            if not self._verify_signature(child, parent):
                raise ValidationError(
                    f"Invalid chain: '{self._get_cn(child)}' "
                    f"is not signed by '{self._get_cn(parent)}'."
                )

        if not self._is_trusted_root(certs[-1]):
            raise ValidationError(
                f"Root CA '{self._get_cn(certs[-1])}' is not in the trusted store."
            )

    def _verify_signature(self, child, parent):
        try:
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
            pub = parent.public_key()
            if isinstance(pub, RSAPublicKey):
                pub.verify(
                    child.signature,
                    child.tbs_certificate_bytes,
                    padding.PKCS1v15(),
                    child.signature_hash_algorithm,
                )
            else:
                pub.verify(
                    child.signature,
                    child.tbs_certificate_bytes,
                    child.signature_hash_algorithm,
                )
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False

    def _is_trusted_root(self, cert):
        fingerprint = cert.fingerprint(hashes.SHA256())
        return any(
            t.fingerprint(hashes.SHA256()) == fingerprint
            for t in self.trusted_root_certs
        )

    def _get_cn(self, cert):
        try:
            return cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        except Exception:
            return "Unknown"

    def _extract_certificate_info(self, cert):
        def get_attr(oid):
            try:
                return cert.subject.get_attributes_for_oid(oid)[0].value
            except Exception:
                return None

        return {
            'subject':      get_attr(NameOID.COMMON_NAME),
            'organization': get_attr(NameOID.ORGANIZATION_NAME),
            'email':        get_attr(NameOID.EMAIL_ADDRESS),
            'issuer':       self._get_cn(cert),
        }


certificate_service = CertificateService()
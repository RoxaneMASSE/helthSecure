#!/usr/bin/env bash
# init.sh - Full initialization of the HealthSecure project
# Generates all Django secrets + configures Keycloak automatically

set -e

echo "============================================"
echo "  HealthSecure - Full initialization"
echo "============================================"
echo ""

# ── Keycloak config ────────────────────────────────────
KC_URL="http://localhost:8080"          # Public URL (via Nginx) → KEYCLOAK_URL in .env
KC_URL_INTERNAL="http://localhost:8180" # Direct internal URL (bypass Nginx) → admin calls
REALM="health"
CLIENT_ID="django-health"
ADMIN="admin"
ADMIN_PASS="admin"

# ── Check if .env already exists ───────────────────────
if [ -f ".env" ]; then
    read -p "The .env file already exists. Replace it? [y/N]: " REPLACE
    if [[ ! "$REPLACE" =~ ^[Yy]$ ]]; then
        echo "✓ .env kept"
        exit 0
    fi
fi

# ── Check required tools ───────────────────────────────
command -v docker >/dev/null || { echo "❌ Docker missing"; exit 1; }
command -v curl   >/dev/null || { echo "❌ curl missing";   exit 1; }
command -v openssl >/dev/null || echo "⚠️  OpenSSL not found (certificates skipped)"
echo "✔ Tools checked"

# ── Find system Python to create the venv ─────────────
SYS_PYTHON=""
if command -v python &>/dev/null; then
    SYS_PYTHON="python"
elif command -v py &>/dev/null; then
    SYS_PYTHON="py"
elif [ -f "/c/python313/python.exe" ]; then
    SYS_PYTHON="/c/python313/python"
elif [ -f "/c/python312/python.exe" ]; then
    SYS_PYTHON="/c/python312/python"
fi

if [ -z "$SYS_PYTHON" ]; then
    echo "❌ Python not found. Please install Python 3.x."
    exit 1
fi
echo "✔ System Python: $SYS_PYTHON"

# ── Create the venv if missing ─────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating venv..."
    $SYS_PYTHON -m venv .venv
    echo "✔ Venv created"
else
    echo "✔ Venv already exists"
fi

# ── Point to the venv Python ──────────────────────────
if [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON_CMD=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
else
    echo "❌ Venv created but Python not found inside it"
    exit 1
fi
echo "✔ Venv Python: $PYTHON_CMD"

# ── Install dependencies in the venv ───────────────────
echo "Installing dependencies..."
$PYTHON_CMD -m pip install --upgrade pip -q
if [ -f "requirements.txt" ]; then
    $PYTHON_CMD -m pip install -r requirements.txt -q
    echo "✔ Dependencies installed"
else
    echo "⚠️  requirements.txt not found, installing minimal packages..."
    $PYTHON_CMD -m pip install django cryptography -q
fi
echo ""

# ── [1/7] Django SECRET_KEY ─────────────────────────────
echo "[1/7] Generating SECRET_KEY..."
SECRET_KEY=$($PYTHON_CMD -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>&1)
if echo "$SECRET_KEY" | grep -q "Error\|Traceback"; then
    echo "❌ Error: $SECRET_KEY"
    echo "   Install Django: pip install django"
    exit 1
fi
echo "✓ Generated"

# ── [2/7] ENCRYPTION_KEY ──────────────────────────────
echo "[2/7] Generating ENCRYPTION_KEY..."
ENCRYPTION_KEY=$($PYTHON_CMD -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>&1)
if echo "$ENCRYPTION_KEY" | grep -q "Error\|Traceback"; then
    echo "❌ Error: $ENCRYPTION_KEY"
    echo "   Install cryptography: pip install cryptography"
    exit 1
fi
echo "✓ Generated"

# ── [3/7] JWT_SECRET_KEY ──────────────────────────────
echo "[3/7] Generating JWT_SECRET_KEY..."
JWT_SECRET_KEY=$($PYTHON_CMD -c "import secrets; print(secrets.token_urlsafe(64))")
echo "✓ Generated"

# ── [4/7] PKI (doctor certificates) ───────────────────
echo "[4/7] Generating PKI..."

# Detect OS for OpenSSL
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    SUBJ_PREFIX="//"
else
    SUBJ_PREFIX="/"
fi

if command -v openssl &>/dev/null; then
    if [ -f "pki/doctors/dr-test-fullchain.pem" ] && \
       [ -f "pki/doctors/dr-test-cert.pem" ] && \
       [ -f "pki/doctors/dr-test-key.pem" ] && \
       [ -f "trusted_cas/root-ca-cert.pem" ]; then
        echo "✓ PKI already present and complete"
    else
        echo "  Generating the full PKI..."
        mkdir -p pki/root-ca pki/intermediate-ca pki/doctors trusted_cas

        openssl genrsa -out pki/root-ca/root-ca-key.pem 4096 2>/dev/null
        openssl req -x509 -new -key pki/root-ca/root-ca-key.pem \
          -out pki/root-ca/root-ca-cert.pem -days 3650 \
          -subj "${SUBJ_PREFIX}C=BE/O=Medical Root CA/CN=Root CA" 2>/dev/null
        echo "  ✓ Root CA"

        openssl genrsa -out pki/intermediate-ca/int-key.pem 4096 2>/dev/null
        openssl req -new -key pki/intermediate-ca/int-key.pem \
          -out pki/intermediate-ca/int-csr.pem \
          -subj "${SUBJ_PREFIX}C=BE/O=CHU Bruxelles/CN=CHU CA" 2>/dev/null
        openssl x509 -req -in pki/intermediate-ca/int-csr.pem \
          -CA pki/root-ca/root-ca-cert.pem \
          -CAkey pki/root-ca/root-ca-key.pem -CAcreateserial \
          -out pki/intermediate-ca/int-cert.pem -days 1825 2>/dev/null
        echo "  ✓ Intermediate CA"

        openssl genrsa -out pki/doctors/dr-test-key.pem 2048 2>/dev/null
        openssl req -new -key pki/doctors/dr-test-key.pem \
          -out pki/doctors/dr-test-csr.pem \
          -subj "${SUBJ_PREFIX}C=BE/O=CHU Bruxelles/CN=Dr. Test/emailAddress=test@chu.be" 2>/dev/null
        openssl x509 -req -in pki/doctors/dr-test-csr.pem \
          -CA pki/intermediate-ca/int-cert.pem \
          -CAkey pki/intermediate-ca/int-key.pem -CAcreateserial \
          -out pki/doctors/dr-test-cert.pem -days 365 2>/dev/null
        echo "  ✓ Dr. Test certificate"

        cat pki/doctors/dr-test-cert.pem \
            pki/intermediate-ca/int-cert.pem \
            pki/root-ca/root-ca-cert.pem \
            > pki/doctors/dr-test-fullchain.pem
        echo "  ✓ Fullchain generated"

        cp pki/root-ca/root-ca-cert.pem trusted_cas/
        cp pki/intermediate-ca/int-cert.pem trusted_cas/
        echo "  ✓ trusted_cas populated"

        echo "✓ PKI generated"
    fi
else
    echo "⚠️  OpenSSL not found, PKI skipped"
    mkdir -p trusted_cas
fi

# ── [5/7] TLS certificates ────────────────────────────
echo "[5/7] Generating TLS certificates..."
if [ -f "cert.crt" ] && [ -f "cert.key" ]; then
    echo "✓ TLS certificates already present"
elif command -v openssl &>/dev/null; then
    openssl req -x509 -newkey rsa:2048 -nodes \
      -keyout cert.key -out cert.crt -days 365 \
      -subj "${SUBJ_PREFIX}CN=localhost" 2>/dev/null
    chmod 600 cert.key
    chmod 644 cert.crt
    echo "✓ TLS certificates generated"
else
    echo "⚠️  OpenSSL not found, TLS skipped"
fi

# ── [6/7] Keycloak (automatic import) ─────────────────
echo "[6/7] Starting Keycloak..."
docker compose -f docker-compose.keycloak.yml up -d

echo "Waiting for Keycloak (can take 30s)..."
until curl -s "${KC_URL_INTERNAL}/realms/master" >/dev/null 2>&1; do
    sleep 3
    echo -n "."
done
echo ""
echo "✔ Keycloak ready"

echo "Waiting for the imported realm '${REALM}'..."
until curl -s "${KC_URL_INTERNAL}/realms/${REALM}" >/dev/null 2>&1; do
    sleep 3
    echo -n "."
done
echo ""
echo "✔ Realm '${REALM}' available (auto import via --import-realm)"

# Admin token
TOKEN=$(curl -s \
  -X POST "${KC_URL_INTERNAL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=admin-cli&username=${ADMIN}&password=${ADMIN_PASS}" \
  | $PYTHON_CMD -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "✔ Admin token obtained"

# Wait for the client to be available after import
echo "Waiting for client '${CLIENT_ID}'..."
CLIENT_UUID=""
until [ -n "$CLIENT_UUID" ]; do
    sleep 3
    echo -n "."
    CLIENT_UUID=$(curl -s \
      -H "Authorization: Bearer $TOKEN" \
      "${KC_URL_INTERNAL}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}" \
      | $PYTHON_CMD -c "
import sys,json
c=json.load(sys.stdin)
if c:
    print(c[0]['id'])
else:
    print('')
" 2>/dev/null) || CLIENT_UUID=""
done
echo ""
echo "✔ Client '${CLIENT_ID}' found"

# Regenerate the client secret (the import sets "**********" as a placeholder)
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "${KC_URL_INTERNAL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/client-secret" > /dev/null
echo "✔ Client secret regenerated"

CLIENT_SECRET=$(curl -s \
  -H "Authorization: Bearer $TOKEN" \
  "${KC_URL_INTERNAL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/client-secret" \
  | $PYTHON_CMD -c "import sys,json; print(json.load(sys.stdin)['value'])")
echo "✔ Client secret retrieved"
echo "✔ Keycloak configuration automatically imported from keycloak/import/realm-export.json"

# ── ELK stack (logs) - optional ────────────────────────
# Optional because it's heavy (Elasticsearch/Logstash/Kibana, ~1.5 GB of images) and not
# required for the app to work: without it, logs are still written
# to logs/security.log and logs/django.log.
read -p "Also start the ELK stack (logs, Elasticsearch/Logstash/Kibana)? [y/N]: " ELK_CHOICE
if [[ "$ELK_CHOICE" =~ ^[Yy]$ ]]; then
    echo "Starting the ELK stack..."
    docker compose -f docker-compose.elk.yml up -d
    echo "Waiting for Elasticsearch..."
    until curl -s "http://localhost:9200/_cluster/health" >/dev/null 2>&1; do
        sleep 3
        echo -n "."
    done
    echo ""
    echo "✔ ELK stack ready"

    echo "Waiting for Kibana..."
    until curl -s "http://localhost:5601/api/status" | grep -q '"level":"available"'; do
        sleep 3
        echo -n "."
    done
    echo ""
    echo "✔ Kibana ready"

    echo "Importing the Kibana data view (django-logs-*)..."
    curl -s -X POST "http://localhost:5601/api/saved_objects/_import?overwrite=true" \
      -H "kbn-xsrf: true" \
      -F "file=@elk/kibana-dataview-import.ndjson" >/dev/null \
      && echo "✔ Data view 'django-logs-*' imported (visible directly in Kibana Discover)" \
      || echo "⚠️  Data view import failed (create it manually in Kibana)"

    LOGSTASH_ENABLED="True"
else
    echo "✓ ELK stack skipped (logs available in logs/security.log and logs/django.log)"
    LOGSTASH_ENABLED="False"
fi

# ── [7/7] Generating .env ──────────────────────────────
echo "[7/7] Generating .env..."

RECAPTCHA_PUBLIC_KEY="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
RECAPTCHA_PRIVATE_KEY="6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"

cat > .env << EOF
# Generated on $(date)
SECRET_KEY=${SECRET_KEY}
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
ENCRYPTION_KEY=${ENCRYPTION_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
WEBAUTHN_RP_ID=localhost
WEBAUTHN_ORIGIN=http://localhost:8000/
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080
RECAPTCHA_PUBLIC_KEY=${RECAPTCHA_PUBLIC_KEY}
RECAPTCHA_PRIVATE_KEY=${RECAPTCHA_PRIVATE_KEY}

KEYCLOAK_URL=${KC_URL}
KEYCLOAK_INTERNAL_URL=${KC_URL_INTERNAL}
KEYCLOAK_REALM=${REALM}
KEYCLOAK_ADMIN_USER=${ADMIN}
KEYCLOAK_ADMIN_PASSWORD=${ADMIN_PASS}

OIDC_RP_CLIENT_ID=${CLIENT_ID}
OIDC_RP_CLIENT_SECRET=${CLIENT_SECRET}

LOGSTASH_ENABLED=${LOGSTASH_ENABLED}
LOGSTASH_HOST=localhost
LOGSTASH_PORT=5000
EOF

chmod 600 .env
echo "✓ .env created"
echo ""

# ── Django migrations ──────────────────────────────────
mkdir -p logs
$PYTHON_CMD manage.py migrate >/dev/null 2>&1 && echo "✔ Migrations applied" || echo "⚠️  Migrations failed (run them manually)"

echo ""
echo "============================================"
echo "  ✓ Initialization complete!"
echo "============================================"
echo ""
echo "Keycloak Admin: http://localhost:8080/admin  (admin/admin)"
if [ "$LOGSTASH_ENABLED" = "True" ]; then
    echo "Kibana (logs)  : http://localhost:5601"
fi
echo ""
echo "Start Django:"
echo "  python manage.py runserver"
echo "  → http://localhost:8000"
echo ""
echo "Or with TLS:"
echo "  python manage.py runserver_plus --cert-file cert.crt"
echo ""

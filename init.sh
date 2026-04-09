#!/usr/bin/env bash
# init.sh - Initialisation complète du projet HealthSecure
# Génère tous les secrets Django + configure Keycloak automatiquement

set -e

echo "============================================"
echo "  HealthSecure - Initialisation complète"
echo "============================================"
echo ""

# ── Config Keycloak ────────────────────────────────────
KC_URL="http://localhost:8080"
REALM="health"
CLIENT_ID="django-health"
ADMIN="admin"
ADMIN_PASS="admin"

# ── Vérifier si .env existe ────────────────────────────
if [ -f ".env" ]; then
    read -p "Le fichier .env existe. Remplacer ? [y/N] : " REPLACE
    if [[ ! "$REPLACE" =~ ^[Yy]$ ]]; then
        echo "✓ .env conservé"
        exit 0
    fi
fi

# ── Vérifier les outils ────────────────────────────────
command -v docker >/dev/null || { echo "❌ Docker manquant"; exit 1; }
command -v curl   >/dev/null || { echo "❌ curl manquant";   exit 1; }
command -v openssl >/dev/null || echo "⚠️  OpenSSL non trouvé (certificats ignorés)"
echo "✔ Outils vérifiés"

# ── Trouver Python système pour créer le venv ─────────
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
    echo "❌ Python non trouvé. Installez Python 3.x."
    exit 1
fi
echo "✔ Python système : $SYS_PYTHON"

# ── Créer le venv si absent ────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Création du venv..."
    $SYS_PYTHON -m venv .venv
    echo "✔ Venv créé"
else
    echo "✔ Venv existant"
fi

# ── Pointer vers le Python du venv ────────────────────
if [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON_CMD=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
else
    echo "❌ Venv créé mais Python introuvable dedans"
    exit 1
fi
echo "✔ Python venv : $PYTHON_CMD"

# ── Installer les dépendances dans le venv ─────────────
echo "Installation des dépendances..."
$PYTHON_CMD -m pip install --upgrade pip -q
if [ -f "requirements.txt" ]; then
    $PYTHON_CMD -m pip install -r requirements.txt -q
    echo "✔ Dépendances installées"
else
    echo "⚠️  requirements.txt introuvable, installation minimale..."
    $PYTHON_CMD -m pip install django cryptography -q
fi
echo ""

# ── [1/7] SECRET_KEY Django ────────────────────────────
echo "[1/7] Génération SECRET_KEY..."
SECRET_KEY=$($PYTHON_CMD -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>&1)
if echo "$SECRET_KEY" | grep -q "Error\|Traceback"; then
    echo "❌ Erreur: $SECRET_KEY"
    echo "   Installez Django : pip install django"
    exit 1
fi
echo "✓ Généré"

# ── [2/7] ENCRYPTION_KEY ──────────────────────────────
echo "[2/7] Génération ENCRYPTION_KEY..."
ENCRYPTION_KEY=$($PYTHON_CMD -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>&1)
if echo "$ENCRYPTION_KEY" | grep -q "Error\|Traceback"; then
    echo "❌ Erreur: $ENCRYPTION_KEY"
    echo "   Installez cryptography : pip install cryptography"
    exit 1
fi
echo "✓ Généré"

# ── [3/7] JWT_SECRET_KEY ──────────────────────────────
echo "[3/7] Génération JWT_SECRET_KEY..."
JWT_SECRET_KEY=$($PYTHON_CMD -c "import secrets; print(secrets.token_urlsafe(64))")
echo "✓ Généré"

# ── [4/7] PKI (certificats médecins) ──────────────────
echo "[4/7] Génération PKI..."

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
        echo "✓ PKI déjà présente et complète"
    else
        echo "  Génération de la PKI complète..."
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
        echo "  ✓ Certificat Dr. Test"

        cat pki/doctors/dr-test-cert.pem \
            pki/intermediate-ca/int-cert.pem \
            pki/root-ca/root-ca-cert.pem \
            > pki/doctors/dr-test-fullchain.pem
        echo "  ✓ Fullchain généré"

        cp pki/root-ca/root-ca-cert.pem trusted_cas/
        cp pki/intermediate-ca/int-cert.pem trusted_cas/
        echo "  ✓ trusted_cas peuplé"
        echo "✓ PKI générée"
    fi
else
    echo "⚠️  OpenSSL non trouvé, PKI ignorée"
    mkdir -p trusted_cas
fi

# ── [5/7] Certificats TLS ─────────────────────────────
echo "[5/7] Génération certificats TLS..."
if [ -f "cert.crt" ] && [ -f "cert.key" ]; then
    echo "✓ Certificats TLS déjà présents"
elif command -v openssl &>/dev/null; then
    openssl req -x509 -newkey rsa:2048 -nodes \
      -keyout cert.key -out cert.crt -days 365 \
      -subj "${SUBJ_PREFIX}CN=localhost" 2>/dev/null
    chmod 600 cert.key
    chmod 644 cert.crt
    echo "✓ Certificats TLS générés"
else
    echo "⚠️  OpenSSL non trouvé, TLS ignoré"
fi

# ── [6/7] Keycloak ────────────────────────────────────
echo "[6/7] Lancement Keycloak..."
docker compose -f docker-compose.keycloak.yml up -d

echo "Attente Keycloak (peut prendre 30s)..."
until curl -s "${KC_URL}/realms/master" >/dev/null 2>&1; do
    sleep 3
    echo -n "."
done
echo ""
echo "✔ Keycloak prêt"

# Token admin
TOKEN=$(curl -s \
  -X POST "${KC_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=admin-cli&username=${ADMIN}&password=${ADMIN_PASS}" \
  | $PYTHON_CMD -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "✔ Token admin obtenu"

# Création realm
REALM_EXISTS=$(curl -s \
  -H "Authorization: Bearer $TOKEN" \
  "${KC_URL}/admin/realms" \
  | $PYTHON_CMD -c "import sys,json; r=json.load(sys.stdin); print(any(x['realm']=='${REALM}' for x in r))")

if [ "$REALM_EXISTS" = "True" ]; then
    echo "✔ Realm '${REALM}' existe déjà"
else
    curl -s -X POST "${KC_URL}/admin/realms" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"realm\":\"${REALM}\",\"enabled\":true}" >/dev/null
    echo "✔ Realm '${REALM}' créé"
fi

# Création roles
for ROLE in doctor patient; do
    curl -s -X POST "${KC_URL}/admin/realms/${REALM}/roles" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"name\":\"$ROLE\"}" >/dev/null 2>&1 || true
    echo "✔ Rôle '$ROLE' créé"
done

# Création client OIDC
CLIENT_EXISTS=$(curl -s \
  -H "Authorization: Bearer $TOKEN" \
  "${KC_URL}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}" \
  | $PYTHON_CMD -c "import sys,json; c=json.load(sys.stdin); print(len(c) > 0)")

if [ "$CLIENT_EXISTS" = "True" ]; then
    echo "✔ Client '${CLIENT_ID}' existe déjà"
else
    curl -s -X POST "${KC_URL}/admin/realms/${REALM}/clients" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "{
        \"clientId\":\"${CLIENT_ID}\",
        \"enabled\":true,
        \"protocol\":\"openid-connect\",
        \"publicClient\":false,
        \"clientAuthenticatorType\":\"client-secret\",
        \"redirectUris\":[
          \"http://localhost:8000/oidc/callback/\",
          \"http://127.0.0.1:8000/oidc/callback/\"
        ],
        \"webOrigins\":[
          \"http://localhost:8000\",
          \"http://127.0.0.1:8000\"
        ]
      }" >/dev/null
    echo "✔ Client OIDC '${CLIENT_ID}' créé"
fi

# Récupérer UUID client
CLIENT_UUID=$(curl -s \
  -H "Authorization: Bearer $TOKEN" \
  "${KC_URL}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}" \
  | $PYTHON_CMD -c "
import sys,json
c=json.load(sys.stdin)
if not c:
    print('❌ Client introuvable après création', file=sys.stderr)
    sys.exit(1)
print(c[0]['id'])
")

CLIENT_SECRET=$(curl -s \
  -H "Authorization: Bearer $TOKEN" \
  "${KC_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/client-secret" \
  | $PYTHON_CMD -c "import sys,json; print(json.load(sys.stdin)['value'])")
echo "✔ Secret client récupéré"

# ── Configuration reCAPTCHA et thème ──────────────────
echo ""
echo "Configuration reCAPTCHA + thème login..."

# 1. Créer le flow "registration captcha" s'il n'existe pas
FLOW_EXISTS=$(curl -s \
  -H "Authorization: Bearer $TOKEN" \
  "${KC_URL}/admin/realms/${REALM}/authentication/flows" \
  | $PYTHON_CMD -c "import sys,json; flows=json.load(sys.stdin); print(any(f['alias']=='registration captcha' for f in flows))")

if [ "$FLOW_EXISTS" = "True" ]; then
    echo "✔ Flow 'registration captcha' existe déjà"
else
    curl -s -X POST "${KC_URL}/admin/realms/${REALM}/authentication/flows/registration/copy" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"newName": "registration captcha"}' >/dev/null
    echo "✔ Flow 'registration captcha' créé"
fi

# 2. Tout configurer en un seul appel : registration, flow, thème, CSP
curl -s -X PUT "${KC_URL}/admin/realms/${REALM}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "registrationAllowed": true,
    "registrationFlow": "registration captcha",
    "loginTheme": "my-theme",
    "browserSecurityHeaders": {
      "contentSecurityPolicy": "frame-src '"'"'self'"'"' https://www.google.com https://www.gstatic.com; frame-ancestors '"'"'self'"'"'; object-src '"'"'none'"'"';",
      "xFrameOptions": "SAMEORIGIN"
    }
  }' >/dev/null && \
  echo "✔ User Registration activé" && \
  echo "✔ Flow 'registration captcha' bindé" && \
  echo "✔ Thème 'my-theme' activé" && \
  echo "✔ CSP configuré" || \
  echo "⚠️  Configuration realm échouée (à faire manuellement dans Keycloak)"

echo "✔ Configuration reCAPTCHA terminée"

# ── [7/7] Génération .env ─────────────────────────────
echo "[7/7] Génération .env..."

RECAPTCHA_PUBLIC_KEY="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
RECAPTCHA_PRIVATE_KEY="6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"

cat > .env << EOF
# Généré le $(date)
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
KEYCLOAK_REALM=${REALM}
KEYCLOAK_ADMIN_USER=${ADMIN}
KEYCLOAK_ADMIN_PASSWORD=${ADMIN_PASS}

OIDC_RP_CLIENT_ID=${CLIENT_ID}
OIDC_RP_CLIENT_SECRET=${CLIENT_SECRET}
EOF

chmod 600 .env
echo "✓ .env créé"
echo ""

# ── Migrations Django ─────────────────────────────────
mkdir -p logs
$PYTHON_CMD manage.py migrate >/dev/null 2>&1 && echo "✔ Migrations appliquées" || echo "⚠️  Migrations échouées (lance-les manuellement)"

echo ""
echo "============================================"
echo "  ✓ Initialisation terminée !"
echo "============================================"
echo ""
echo "Keycloak Admin : http://localhost:8080/admin  (admin/admin)"
echo ""
echo "Lancer Django :"
echo "  python manage.py runserver"
echo "  → http://localhost:8000"
echo ""
echo "Ou avec TLS :"
echo "  python manage.py runserver_plus --cert-file cert.crt"
echo ""
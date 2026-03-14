#!/bin/bash
# init.sh - Initialisation sécurisée du projet
# Génère automatiquement TOUS les secrets

set -e

echo "============================================"
echo "  Medical Records - Initialisation"
echo "============================================"
echo ""

# Vérifier si .env existe
if [ -f ".env" ]; then
    read -p "Le fichier .env existe. Remplacer ? [y/N] : " REPLACE
    if [[ ! "$REPLACE" =~ ^[Yy]$ ]]; then
        echo "✓ .env conservé"
        exit 0
    fi
fi

# Déterminer la commande Python disponible
PYTHON_CMD=""

# Vérifier si on est dans un environnement virtuel
if [ -f ".venv/Scripts/python.exe" ]; then
    # Windows (Git Bash)
    PYTHON_CMD=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
    # Linux/Mac
    PYTHON_CMD=".venv/bin/python"
elif [ ! -z "$VIRTUAL_ENV" ]; then
    # Environnement déjà activé
    PYTHON_CMD="python"
else
    # Chercher Python système
    if command -v python3 &> /dev/null && python3 --version &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null && python --version &> /dev/null; then
        PYTHON_CMD="python"
    elif command -v py &> /dev/null && py --version &> /dev/null; then
        PYTHON_CMD="py"
    elif [ -f "/c/Python313/python.exe" ]; then
        PYTHON_CMD="/c/Python313/python"
    elif [ -f "/c/Python312/python.exe" ]; then
        PYTHON_CMD="/c/Python312/python"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Python non trouvé"
    echo "   Créez d'abord un environnement virtuel :"
    echo "   python -m venv .venv"
    echo "   source .venv/Scripts/activate  # Windows/Git Bash"
    exit 1
fi

echo "Python : $PYTHON_CMD"
echo ""

echo "[1/4] Génération SECRET_KEY..."
SECRET_KEY=$($PYTHON_CMD -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>&1)
if echo "$SECRET_KEY" | grep -q "Error\|Traceback"; then
    echo "❌ Erreur: $SECRET_KEY"
    echo "   Installez Django : pip install django"
    exit 1
fi
echo "✓ Généré"

echo "[2/4] Génération ENCRYPTION_KEY..."
ENCRYPTION_KEY=$($PYTHON_CMD -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>&1)
if echo "$ENCRYPTION_KEY" | grep -q "Error\|Traceback"; then
    echo "❌ Erreur: $ENCRYPTION_KEY"
    echo "   Installez cryptography : pip install cryptography"
    exit 1
fi
echo "✓ Généré"

echo "[3/4] Génération JWT_SECRET_KEY..."
JWT_SECRET_KEY=$($PYTHON_CMD -c "import secrets; print(secrets.token_urlsafe(64))")
echo "✓ Généré"

echo "[4/4] Configuration reCAPTCHA..."
RECAPTCHA_PUBLIC_KEY="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
RECAPTCHA_PRIVATE_KEY="6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"
echo "✓ Clés de test Google"
echo ""

# Créer .env
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
EOF

chmod 600 .env
echo "✓ .env créé"
echo ""

# Détecter l'OS pour les certificats OpenSSL
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows (Git Bash) - utilise MSYS
    SUBJ_PREFIX="//"
else
    # Linux/Mac
    SUBJ_PREFIX="/"
fi

echo "[5/6] Génération PKI..."
if command -v openssl &> /dev/null; then
    if [ -d "pki" ] && [ -f "pki/doctors/dr-test-fullchain.pem" ]; then
        echo "✓ PKI déjà présente"
    else
        mkdir -p pki/root-ca pki/intermediate-ca pki/doctors trusted_cas
        
        # Root CA
        openssl genrsa -out pki/root-ca/root-ca-key.pem 4096 2>/dev/null
        openssl req -x509 -new -key pki/root-ca/root-ca-key.pem \
          -out pki/root-ca/root-ca-cert.pem -days 3650 \
          -subj "${SUBJ_PREFIX}C=BE/O=Medical Root CA/CN=Root CA"
        
        # Intermediate CA
        openssl genrsa -out pki/intermediate-ca/int-key.pem 4096 2>/dev/null
        openssl req -new -key pki/intermediate-ca/int-key.pem \
          -out pki/intermediate-ca/int-csr.pem \
          -subj "${SUBJ_PREFIX}C=BE/O=CHU Bruxelles/CN=CHU CA"
        openssl x509 -req -in pki/intermediate-ca/int-csr.pem \
          -CA pki/root-ca/root-ca-cert.pem \
          -CAkey pki/root-ca/root-ca-key.pem -CAcreateserial \
          -out pki/intermediate-ca/int-cert.pem -days 1825
        
        # Certificat docteur
        openssl genrsa -out pki/doctors/dr-test-key.pem 2048 2>/dev/null
        openssl req -new -key pki/doctors/dr-test-key.pem \
          -out pki/doctors/dr-test-csr.pem \
          -subj "${SUBJ_PREFIX}C=BE/O=CHU Bruxelles/CN=Dr. Test/emailAddress=test@chu.be"
        openssl x509 -req -in pki/doctors/dr-test-csr.pem \
          -CA pki/intermediate-ca/int-cert.pem \
          -CAkey pki/intermediate-ca/int-key.pem -CAcreateserial \
          -out pki/doctors/dr-test-cert.pem -days 365
        
        # Fullchain
        cat pki/doctors/dr-test-cert.pem \
            pki/intermediate-ca/int-cert.pem \
            pki/root-ca/root-ca-cert.pem \
            > pki/doctors/dr-test-fullchain.pem
        
        cp pki/root-ca/root-ca-cert.pem trusted_cas/
        
        echo "✓ PKI générée"
    fi
else
    echo "⚠️  OpenSSL non trouvé"
    mkdir -p trusted_cas
fi
echo ""

echo "[6/6] Génération certificats TLS..."
if [ -f "cert.crt" ] && [ -f "cert.key" ]; then
    echo "✓ Certificats TLS déjà présents"
else
    if command -v openssl &> /dev/null; then
        openssl req -x509 -newkey rsa:2048 -nodes \
          -keyout cert.key -out cert.crt -days 365 \
          -subj "${SUBJ_PREFIX}CN=localhost"
        chmod 600 cert.key
        chmod 644 cert.crt
        echo "✓ Certificats TLS générés"
    else
        echo "⚠️  OpenSSL non trouvé"
    fi
fi

echo ""
echo "============================================"
echo "  ✓ Configuration terminée"
echo "============================================"
echo ""
echo "Prochaines étapes :"
echo "  pip install -r requirements.txt"
echo "  mkdir -p logs"
echo "  python manage.py migrate"
echo "  python manage.py createsuperuser"
echo "  python manage.py runserver_plus --cert-file cert.crt"
echo ""
# init.ps1 - Initialisation complète du projet HealthSecure
# Génère tous les secrets Django + configure Keycloak automatiquement
$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  HealthSecure - Initialisation complète"   -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Config Keycloak ────────────────────────────────────
$KC_URL    = "http://localhost:8080"
$REALM     = "health"
$CLIENT_ID = "django-health"
$ADMIN     = "admin"
$ADMIN_PASS= "admin"

# ── Vérifier si .env existe ────────────────────────────
if (Test-Path ".env") {
    $REPLACE = Read-Host "Le fichier .env existe. Remplacer ? [y/N]"
    if ($REPLACE -notmatch "^[Yy]$") {
        Write-Host "✓ .env conservé" -ForegroundColor Green
        exit 0
    }
}

# ── Vérifier les outils ────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker manquant" -ForegroundColor Red; exit 1
}
if (-not (Get-Command openssl -ErrorAction SilentlyContinue)) {
    Write-Host "⚠️  OpenSSL non trouvé (certificats ignorés)" -ForegroundColor Yellow
}
Write-Host "✔ Outils vérifiés" -ForegroundColor Green

# ── Déterminer Python ──────────────────────────────────
$PYTHON_CMD = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $PYTHON_CMD = ".venv\Scripts\python.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PYTHON_CMD = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PYTHON_CMD = "python3"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PYTHON_CMD = "py"
} elseif (Test-Path "C:\Python313\python.exe") {
    $PYTHON_CMD = "C:\Python313\python.exe"
} elseif (Test-Path "C:\Python312\python.exe") {
    $PYTHON_CMD = "C:\Python312\python.exe"
}

if (-not $PYTHON_CMD) {
    Write-Host "❌ Python non trouvé. Créez un venv : python -m venv .venv" -ForegroundColor Red
    exit 1
}
Write-Host "✔ Python : $PYTHON_CMD" -ForegroundColor Green
Write-Host ""

# ── [1/7] SECRET_KEY Django ────────────────────────────
Write-Host "[1/7] Génération SECRET_KEY..."
$SECRET_KEY = & $PYTHON_CMD -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>&1
if ($SECRET_KEY -match "Error|Traceback") {
    Write-Host "❌ Erreur: $SECRET_KEY" -ForegroundColor Red
    Write-Host "   Installez Django : pip install django"
    exit 1
}
Write-Host "✓ Généré" -ForegroundColor Green

# ── [2/7] ENCRYPTION_KEY ──────────────────────────────
Write-Host "[2/7] Génération ENCRYPTION_KEY..."
$ENCRYPTION_KEY = & $PYTHON_CMD -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>&1
if ($ENCRYPTION_KEY -match "Error|Traceback") {
    Write-Host "❌ Erreur: $ENCRYPTION_KEY" -ForegroundColor Red
    Write-Host "   Installez cryptography : pip install cryptography"
    exit 1
}
Write-Host "✓ Généré" -ForegroundColor Green

# ── [3/7] JWT_SECRET_KEY ──────────────────────────────
Write-Host "[3/7] Génération JWT_SECRET_KEY..."
$JWT_SECRET_KEY = & $PYTHON_CMD -c "import secrets; print(secrets.token_urlsafe(64))"
Write-Host "✓ Généré" -ForegroundColor Green

# ── [4/7] PKI ─────────────────────────────────────────
Write-Host "[4/7] Génération PKI..."
if (Get-Command openssl -ErrorAction SilentlyContinue) {
    if ((Test-Path "pki") -and (Test-Path "pki\doctors\dr-test-fullchain.pem")) {
        Write-Host "✓ PKI déjà présente" -ForegroundColor Green
    } else {
        New-Item -ItemType Directory -Force -Path "pki\root-ca","pki\intermediate-ca","pki\doctors","trusted_cas" | Out-Null

        # Root CA
        openssl genrsa -out pki\root-ca\root-ca-key.pem 4096 2>$null
        openssl req -x509 -new -key pki\root-ca\root-ca-key.pem `
          -out pki\root-ca\root-ca-cert.pem -days 3650 `
          -subj "/C=BE/O=Medical Root CA/CN=Root CA"

        # Intermediate CA
        openssl genrsa -out pki\intermediate-ca\int-key.pem 4096 2>$null
        openssl req -new -key pki\intermediate-ca\int-key.pem `
          -out pki\intermediate-ca\int-csr.pem `
          -subj "/C=BE/O=CHU Bruxelles/CN=CHU CA"
        openssl x509 -req -in pki\intermediate-ca\int-csr.pem `
          -CA pki\root-ca\root-ca-cert.pem `
          -CAkey pki\root-ca\root-ca-key.pem -CAcreateserial `
          -out pki\intermediate-ca\int-cert.pem -days 1825 2>$null

        # Certificat docteur
        openssl genrsa -out pki\doctors\dr-test-key.pem 2048 2>$null
        openssl req -new -key pki\doctors\dr-test-key.pem `
          -out pki\doctors\dr-test-csr.pem `
          -subj "/C=BE/O=CHU Bruxelles/CN=Dr. Test/emailAddress=test@chu.be"
        openssl x509 -req -in pki\doctors\dr-test-csr.pem `
          -CA pki\intermediate-ca\int-cert.pem `
          -CAkey pki\intermediate-ca\int-key.pem -CAcreateserial `
          -out pki\doctors\dr-test-cert.pem -days 365 2>$null

        # Fullchain
        Get-Content pki\doctors\dr-test-cert.pem, pki\intermediate-ca\int-cert.pem, pki\root-ca\root-ca-cert.pem `
          | Set-Content pki\doctors\dr-test-fullchain.pem

        Copy-Item pki\root-ca\root-ca-cert.pem trusted_cas\
        Write-Host "✓ PKI générée" -ForegroundColor Green
    }
} else {
    Write-Host "⚠️  OpenSSL non trouvé, PKI ignorée" -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path "trusted_cas" | Out-Null
}

# ── [5/7] Certificats TLS ─────────────────────────────
Write-Host "[5/7] Génération certificats TLS..."
if ((Test-Path "cert.crt") -and (Test-Path "cert.key")) {
    Write-Host "✓ Certificats TLS déjà présents" -ForegroundColor Green
} elseif (Get-Command openssl -ErrorAction SilentlyContinue) {
    openssl req -x509 -newkey rsa:2048 -nodes `
      -keyout cert.key -out cert.crt -days 365 `
      -subj "/CN=localhost" 2>$null
    Write-Host "✓ Certificats TLS générés" -ForegroundColor Green
} else {
    Write-Host "⚠️  OpenSSL non trouvé, TLS ignoré" -ForegroundColor Yellow
}

# ── [6/7] Keycloak ────────────────────────────────────
Write-Host "[6/7] Lancement Keycloak..."
docker compose -f docker-compose.keycloak.yml up -d

Write-Host "Attente Keycloak (peut prendre 30s)..." -NoNewline
do {
    Start-Sleep 3
    Write-Host "." -NoNewline
    try {
        $resp = Invoke-WebRequest -Uri "$KC_URL/realms/master" -UseBasicParsing -ErrorAction SilentlyContinue
        $ready = $resp.StatusCode -eq 200
    } catch { $ready = $false }
} while (-not $ready)
Write-Host ""
Write-Host "✔ Keycloak prêt" -ForegroundColor Green

# Token admin
$tokenBody = "grant_type=password&client_id=admin-cli&username=$ADMIN&password=$ADMIN_PASS"
$tokenResp  = Invoke-RestMethod -Method Post `
  -Uri "$KC_URL/realms/master/protocol/openid-connect/token" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body $tokenBody
$TOKEN = $tokenResp.access_token
Write-Host "✔ Token admin obtenu" -ForegroundColor Green

$headers = @{ Authorization = "Bearer $TOKEN"; "Content-Type" = "application/json" }

# Création realm
$realms = Invoke-RestMethod -Uri "$KC_URL/admin/realms" -Headers $headers
if ($realms | Where-Object { $_.realm -eq $REALM }) {
    Write-Host "✔ Realm '$REALM' existe déjà" -ForegroundColor Green
} else {
    Invoke-RestMethod -Method Post -Uri "$KC_URL/admin/realms" -Headers $headers `
      -Body '{"realm":"' + $REALM + '","enabled":true}' | Out-Null
    Write-Host "✔ Realm '$REALM' créé" -ForegroundColor Green
}

# Création roles
foreach ($ROLE in @("doctor", "patient")) {
    try {
        Invoke-RestMethod -Method Post -Uri "$KC_URL/admin/realms/$REALM/roles" `
          -Headers $headers -Body "{`"name`":`"$ROLE`"}" | Out-Null
    } catch {}
    Write-Host "✔ Rôle '$ROLE' créé" -ForegroundColor Green
}

# Création client OIDC
$existingClients = Invoke-RestMethod -Uri "$KC_URL/admin/realms/$REALM/clients?clientId=$CLIENT_ID" -Headers $headers
if ($existingClients.Count -gt 0) {
    Write-Host "✔ Client '$CLIENT_ID' existe déjà" -ForegroundColor Green
    $CLIENT_UUID = $existingClients[0].id
} else {
    $clientBody = @{
        clientId               = $CLIENT_ID
        enabled                = $true
        protocol               = "openid-connect"
        publicClient           = $false
        clientAuthenticatorType = "client-secret"
        redirectUris           = @("http://localhost:8000/oidc/callback/", "http://127.0.0.1:8000/oidc/callback/")
        webOrigins             = @("http://localhost:8000", "http://127.0.0.1:8000")
    } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "$KC_URL/admin/realms/$REALM/clients" `
      -Headers $headers -Body $clientBody | Out-Null
    Write-Host "✔ Client OIDC '$CLIENT_ID' créé" -ForegroundColor Green
    $existingClients = Invoke-RestMethod -Uri "$KC_URL/admin/realms/$REALM/clients?clientId=$CLIENT_ID" -Headers $headers
    $CLIENT_UUID = $existingClients[0].id
}

# Secret client
$secretResp   = Invoke-RestMethod -Uri "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/client-secret" -Headers $headers
$CLIENT_SECRET = $secretResp.value
Write-Host "✔ Secret client récupéré" -ForegroundColor Green

# ── [7/7] Génération .env ─────────────────────────────
Write-Host "[7/7] Génération .env..."

$RECAPTCHA_PUBLIC_KEY  = "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
$RECAPTCHA_PRIVATE_KEY = "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"
$DATE = Get-Date -Format "ddd, MMM dd, yyyy hh:mm:ss tt"

@"
# Généré le $DATE
SECRET_KEY=$SECRET_KEY
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
ENCRYPTION_KEY=$ENCRYPTION_KEY
JWT_SECRET_KEY=$JWT_SECRET_KEY
WEBAUTHN_RP_ID=localhost
WEBAUTHN_ORIGIN=http://localhost:8000/
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080
RECAPTCHA_PUBLIC_KEY=$RECAPTCHA_PUBLIC_KEY
RECAPTCHA_PRIVATE_KEY=$RECAPTCHA_PRIVATE_KEY

KEYCLOAK_URL=$KC_URL
KEYCLOAK_REALM=$REALM
KEYCLOAK_ADMIN_USER=$ADMIN
KEYCLOAK_ADMIN_PASSWORD=$ADMIN_PASS

OIDC_RP_CLIENT_ID=$CLIENT_ID
OIDC_RP_CLIENT_SECRET=$CLIENT_SECRET
"@ | Set-Content -Encoding UTF8 .env

Write-Host "✓ .env créé" -ForegroundColor Green
Write-Host ""

# ── Migrations Django ─────────────────────────────────
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
try {
    & $PYTHON_CMD manage.py migrate | Out-Null
    Write-Host "✔ Migrations appliquées" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Migrations échouées (lance-les manuellement)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ✓ Initialisation terminée !"              -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Keycloak Admin : http://localhost:8080/admin  (admin/admin)"
Write-Host ""
Write-Host "Lancer Django :"
Write-Host "  python manage.py runserver"
Write-Host "  -> http://localhost:8000"
Write-Host ""
Write-Host "Ou avec TLS :"
Write-Host "  python manage.py runserver_plus --cert-file cert.crt"
Write-Host ""
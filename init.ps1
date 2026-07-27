# init.ps1 - Full initialization of the HealthSecure project
# Generates all Django secrets + configures Keycloak automatically
$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  HealthSecure - Full initialization"        -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Keycloak config ────────────────────────────────────
$KC_URL          = "http://localhost:8080"   # Public URL (via Nginx) → KEYCLOAK_URL in .env
$KC_URL_INTERNAL = "http://localhost:8180"   # Direct internal URL (bypass Nginx) → admin calls
$REALM     = "health"
$CLIENT_ID = "django-health"
$ADMIN     = "admin"
$ADMIN_PASS= "admin"

# ── Check if .env already exists ───────────────────────
if (Test-Path ".env") {
    $REPLACE = Read-Host "The .env file already exists. Replace it? [y/N]"
    if ($REPLACE -notmatch "^[Yy]$") {
        Write-Host "✓ .env kept" -ForegroundColor Green
        exit 0
    }
}

# ── Check required tools ───────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker missing" -ForegroundColor Red; exit 1
}
if (-not (Get-Command openssl -ErrorAction SilentlyContinue)) {
    Write-Host "⚠️  OpenSSL not found (certificates skipped)" -ForegroundColor Yellow
}
Write-Host "✔ Tools checked" -ForegroundColor Green

# ── Find system Python to create the venv ─────────────
$SYS_PYTHON = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $SYS_PYTHON = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $SYS_PYTHON = "py"
} elseif (Test-Path "C:\Python313\python.exe") {
    $SYS_PYTHON = "C:\Python313\python.exe"
} elseif (Test-Path "C:\Python312\python.exe") {
    $SYS_PYTHON = "C:\Python312\python.exe"
}

if (-not $SYS_PYTHON) {
    Write-Host "❌ Python not found. Please install Python 3.x." -ForegroundColor Red
    exit 1
}
Write-Host "✔ System Python: $SYS_PYTHON" -ForegroundColor Green

# ── Create the venv if missing ─────────────────────────
if (-not (Test-Path ".venv")) {
    Write-Host "Creating venv..."
    & $SYS_PYTHON -m venv .venv
    Write-Host "✔ Venv created" -ForegroundColor Green
} else {
    Write-Host "✔ Venv already exists" -ForegroundColor Green
}

# ── Point to the venv Python ──────────────────────────
if (Test-Path ".venv\Scripts\python.exe") {
    $PYTHON_CMD = ".venv\Scripts\python.exe"
} else {
    Write-Host "❌ Venv created but Python not found inside it" -ForegroundColor Red
    exit 1
}
Write-Host "✔ Venv Python: $PYTHON_CMD" -ForegroundColor Green

# ── Install dependencies in the venv ───────────────────
Write-Host "Installing dependencies..."
& $PYTHON_CMD -m pip install --upgrade pip -q
if (Test-Path "requirements.txt") {
    & $PYTHON_CMD -m pip install -r requirements.txt -q
    Write-Host "✔ Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "⚠️  requirements.txt not found, installing minimal packages..." -ForegroundColor Yellow
    & $PYTHON_CMD -m pip install django cryptography -q
}
Write-Host ""

# ── [1/7] Django SECRET_KEY ─────────────────────────────
Write-Host "[1/7] Generating SECRET_KEY..."
$SECRET_KEY = & $PYTHON_CMD -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>&1
if ($SECRET_KEY -match "Error|Traceback") {
    Write-Host "❌ Error: $SECRET_KEY" -ForegroundColor Red
    Write-Host "   Install Django: pip install django"
    exit 1
}
Write-Host "✓ Generated" -ForegroundColor Green

# ── [2/7] ENCRYPTION_KEY ──────────────────────────────
Write-Host "[2/7] Generating ENCRYPTION_KEY..."
$ENCRYPTION_KEY = & $PYTHON_CMD -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>&1
if ($ENCRYPTION_KEY -match "Error|Traceback") {
    Write-Host "❌ Error: $ENCRYPTION_KEY" -ForegroundColor Red
    Write-Host "   Install cryptography: pip install cryptography"
    exit 1
}
Write-Host "✓ Generated" -ForegroundColor Green

# ── [3/7] JWT_SECRET_KEY ──────────────────────────────
Write-Host "[3/7] Generating JWT_SECRET_KEY..."
$JWT_SECRET_KEY = & $PYTHON_CMD -c "import secrets; print(secrets.token_urlsafe(64))"
Write-Host "✓ Generated" -ForegroundColor Green

# ── [4/7] PKI (doctor certificates) ───────────────────
Write-Host "[4/7] Generating PKI..."
if (Get-Command openssl -ErrorAction SilentlyContinue) {
    if ((Test-Path "pki\doctors\dr-test-fullchain.pem") -and `
        (Test-Path "pki\doctors\dr-test-cert.pem") -and `
        (Test-Path "pki\doctors\dr-test-key.pem") -and `
        (Test-Path "trusted_cas\root-ca-cert.pem")) {
        Write-Host "✓ PKI already present and complete" -ForegroundColor Green
    } else {
        Write-Host "  Generating the full PKI..."
        New-Item -ItemType Directory -Force -Path "pki\root-ca","pki\intermediate-ca","pki\doctors","trusted_cas" | Out-Null

        # Root CA
        openssl genrsa -out pki\root-ca\root-ca-key.pem 4096 2>$null
        openssl req -x509 -new -key pki\root-ca\root-ca-key.pem `
          -out pki\root-ca\root-ca-cert.pem -days 3650 `
          -subj "/C=BE/O=Medical Root CA/CN=Root CA" 2>$null
        Write-Host "  ✓ Root CA"

        # Intermediate CA
        openssl genrsa -out pki\intermediate-ca\int-key.pem 4096 2>$null
        openssl req -new -key pki\intermediate-ca\int-key.pem `
          -out pki\intermediate-ca\int-csr.pem `
          -subj "/C=BE/O=CHU Bruxelles/CN=CHU CA" 2>$null
        openssl x509 -req -in pki\intermediate-ca\int-csr.pem `
          -CA pki\root-ca\root-ca-cert.pem `
          -CAkey pki\root-ca\root-ca-key.pem -CAcreateserial `
          -out pki\intermediate-ca\int-cert.pem -days 1825 2>$null
        Write-Host "  ✓ Intermediate CA"

        # Doctor certificate
        openssl genrsa -out pki\doctors\dr-test-key.pem 2048 2>$null
        openssl req -new -key pki\doctors\dr-test-key.pem `
          -out pki\doctors\dr-test-csr.pem `
          -subj "/C=BE/O=CHU Bruxelles/CN=Dr. Test/emailAddress=test@chu.be" 2>$null
        openssl x509 -req -in pki\doctors\dr-test-csr.pem `
          -CA pki\intermediate-ca\int-cert.pem `
          -CAkey pki\intermediate-ca\int-key.pem -CAcreateserial `
          -out pki\doctors\dr-test-cert.pem -days 365 2>$null
        Write-Host "  ✓ Dr. Test certificate"

        # Fullchain
        Get-Content pki\doctors\dr-test-cert.pem, pki\intermediate-ca\int-cert.pem, pki\root-ca\root-ca-cert.pem `
          | Set-Content pki\doctors\dr-test-fullchain.pem
        Write-Host "  ✓ Fullchain generated"

        Copy-Item pki\root-ca\root-ca-cert.pem trusted_cas\
        Copy-Item pki\intermediate-ca\int-cert.pem trusted_cas\
        Write-Host "  ✓ trusted_cas populated"

        Write-Host "✓ PKI generated" -ForegroundColor Green
    }
} else {
    Write-Host "⚠️  OpenSSL not found, PKI skipped" -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path "trusted_cas" | Out-Null
}

# ── [5/7] TLS certificates ────────────────────────────
Write-Host "[5/7] Generating TLS certificates..."
if ((Test-Path "cert.crt") -and (Test-Path "cert.key")) {
    Write-Host "✓ TLS certificates already present" -ForegroundColor Green
} elseif (Get-Command openssl -ErrorAction SilentlyContinue) {
    openssl req -x509 -newkey rsa:2048 -nodes `
      -keyout cert.key -out cert.crt -days 365 `
      -subj "/CN=localhost" 2>$null
    Write-Host "✓ TLS certificates generated" -ForegroundColor Green
} else {
    Write-Host "⚠️  OpenSSL not found, TLS skipped" -ForegroundColor Yellow
}

# ── [6/7] Keycloak (automatic import) ─────────────────
Write-Host "[6/7] Starting Keycloak..."
docker compose -f docker-compose.keycloak.yml up -d

Write-Host "Waiting for Keycloak (can take 30s)..." -NoNewline
do {
    Start-Sleep 3
    Write-Host "." -NoNewline
    try {
        $resp = Invoke-WebRequest -Uri "$KC_URL_INTERNAL/realms/master" -UseBasicParsing -ErrorAction SilentlyContinue
        $ready = $resp.StatusCode -eq 200
    } catch { $ready = $false }
} while (-not $ready)
Write-Host ""
Write-Host "✔ Keycloak ready" -ForegroundColor Green

Write-Host "Waiting for the imported realm '$REALM'..." -NoNewline
$realmReady = $false
do {
    Start-Sleep 3
    Write-Host "." -NoNewline
    try {
        $resp = Invoke-WebRequest -Uri "$KC_URL_INTERNAL/realms/$REALM" -UseBasicParsing -ErrorAction SilentlyContinue
        $realmReady = $resp.StatusCode -eq 200
    } catch { $realmReady = $false }
} while (-not $realmReady)
Write-Host ""
Write-Host "✔ Realm '$REALM' available (auto import via --import-realm)" -ForegroundColor Green

# Admin token
$tokenBody = "grant_type=password&client_id=admin-cli&username=$ADMIN&password=$ADMIN_PASS"
$tokenResp  = Invoke-RestMethod -Method Post `
  -Uri "$KC_URL_INTERNAL/realms/master/protocol/openid-connect/token" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body $tokenBody
$TOKEN = $tokenResp.access_token
Write-Host "✔ Admin token obtained" -ForegroundColor Green

$headers = @{ Authorization = "Bearer $TOKEN"; "Content-Type" = "application/json" }

# Wait for the client to be available after import
Write-Host "Waiting for client '$CLIENT_ID'..." -NoNewline
$CLIENT_UUID = ""
do {
    Start-Sleep 3
    Write-Host "." -NoNewline
    try {
        $clients = Invoke-RestMethod -Uri "$KC_URL_INTERNAL/admin/realms/$REALM/clients?clientId=$CLIENT_ID" -Headers $headers -ErrorAction SilentlyContinue
        if ($clients -and $clients.Count -gt 0) {
            $CLIENT_UUID = $clients[0].id
        }
    } catch { $CLIENT_UUID = "" }
} while (-not $CLIENT_UUID)
Write-Host ""
Write-Host "✔ Client '$CLIENT_ID' found" -ForegroundColor Green

# Regenerate the client secret (the import sets "**********" as a placeholder)
Invoke-RestMethod -Method Post -Uri "$KC_URL_INTERNAL/admin/realms/$REALM/clients/$CLIENT_UUID/client-secret" -Headers $headers | Out-Null
Write-Host "✔ Client secret regenerated" -ForegroundColor Green

# Retrieve the new secret
$secretResp   = Invoke-RestMethod -Uri "$KC_URL_INTERNAL/admin/realms/$REALM/clients/$CLIENT_UUID/client-secret" -Headers $headers
$CLIENT_SECRET = $secretResp.value
Write-Host "✔ Client secret retrieved" -ForegroundColor Green
Write-Host "✔ Keycloak configuration automatically imported from keycloak/import/realm-export.json" -ForegroundColor Green

# ── ELK stack (logs) - optional ────────────────────────
# Optional because it's heavy (Elasticsearch/Logstash/Kibana, ~1.5 GB of images) and not
# required for the app to work: without it, logs are still written
# to logs/security.log and logs/django.log.
$ELK_CHOICE = Read-Host "Also start the ELK stack (logs, Elasticsearch/Logstash/Kibana)? [y/N]"
if ($ELK_CHOICE -match "^[Yy]$") {
    Write-Host "Starting the ELK stack..."
    docker compose -f docker-compose.elk.yml up -d
    Write-Host "Waiting for Elasticsearch..." -NoNewline
    $esReady = $false
    do {
        Start-Sleep 3
        Write-Host "." -NoNewline
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:9200/_cluster/health" -UseBasicParsing -ErrorAction SilentlyContinue
            $esReady = $resp.StatusCode -eq 200
        } catch { $esReady = $false }
    } while (-not $esReady)
    Write-Host ""
    Write-Host "✔ ELK stack ready" -ForegroundColor Green

    Write-Host "Waiting for Kibana..." -NoNewline
    $kbReady = $false
    do {
        Start-Sleep 3
        Write-Host "." -NoNewline
        try {
            $resp = Invoke-RestMethod -Uri "http://localhost:5601/api/status" -ErrorAction SilentlyContinue
            $kbReady = $resp.status.overall.level -eq "available"
        } catch { $kbReady = $false }
    } while (-not $kbReady)
    Write-Host ""
    Write-Host "✔ Kibana ready" -ForegroundColor Green

    Write-Host "Importing the Kibana data view (django-logs-*)..."
    try {
        $form = @{ file = Get-Item "elk\kibana-dataview-import.ndjson" }
        Invoke-RestMethod -Method Post `
          -Uri "http://localhost:5601/api/saved_objects/_import?overwrite=true" `
          -Headers @{ "kbn-xsrf" = "true" } `
          -Form $form | Out-Null
        Write-Host "✔ Data view 'django-logs-*' imported (visible directly in Kibana Discover)" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Data view import failed (create it manually in Kibana)" -ForegroundColor Yellow
    }

    $LOGSTASH_ENABLED = "True"
} else {
    Write-Host "✓ ELK stack skipped (logs available in logs/security.log and logs/django.log)" -ForegroundColor Green
    $LOGSTASH_ENABLED = "False"
}

# ── [7/7] Generating .env ──────────────────────────────
Write-Host "[7/7] Generating .env..."

$RECAPTCHA_PUBLIC_KEY  = "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
$RECAPTCHA_PRIVATE_KEY = "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"
$DATE = Get-Date -Format "ddd, MMM dd, yyyy hh:mm:ss tt"

@"
# Generated on $DATE
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
KEYCLOAK_INTERNAL_URL=$KC_URL_INTERNAL
KEYCLOAK_REALM=$REALM
KEYCLOAK_ADMIN_USER=$ADMIN
KEYCLOAK_ADMIN_PASSWORD=$ADMIN_PASS

OIDC_RP_CLIENT_ID=$CLIENT_ID
OIDC_RP_CLIENT_SECRET=$CLIENT_SECRET

LOGSTASH_ENABLED=$LOGSTASH_ENABLED
LOGSTASH_HOST=localhost
LOGSTASH_PORT=5000
"@ | Set-Content -Encoding UTF8 .env

Write-Host "✓ .env created" -ForegroundColor Green
Write-Host ""

# ── Django migrations ──────────────────────────────────
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
try {
    & $PYTHON_CMD manage.py migrate | Out-Null
    Write-Host "✔ Migrations applied" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Migrations failed (run them manually)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ✓ Initialization complete!"                -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Keycloak Admin: http://localhost:8080/admin  (admin/admin)"
if ($LOGSTASH_ENABLED -eq "True") {
    Write-Host "Kibana (logs)  : http://localhost:5601"
}
Write-Host ""
Write-Host "Start Django:"
Write-Host "  python manage.py runserver"
Write-Host "  -> http://localhost:8000"
Write-Host ""
Write-Host "Or with TLS:"
Write-Host "  python manage.py runserver_plus --cert-file cert.crt"
Write-Host ""

# init.ps1 - Initialisation sécurisée du projet (Windows)

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Medical Records - Initialisation" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Vérifier si .env existe
if (Test-Path .env) {
    $REPLACE = Read-Host "Le fichier .env existe. Remplacer ? [y/N]"
    if ($REPLACE -notmatch "^[Yy]$") {
        Write-Host "OK .env conserve" -ForegroundColor Green
        exit 0
    }
}

# CORRECTION: Utiliser le Python de l'environnement virtuel
$PYTHON_CMD = $null

# Vérifier si l'environnement virtuel existe et est activé
if (Test-Path ".venv\Scripts\python.exe") {
    $PYTHON_CMD = ".venv\Scripts\python.exe"
    Write-Host "Utilisation du Python de l'environnement virtuel" -ForegroundColor Cyan
} elseif ($env:VIRTUAL_ENV) {
    # L'environnement est déjà activé
    $PYTHON_CMD = "python"
    Write-Host "Environnement virtuel deja active" -ForegroundColor Cyan
} else {
    Write-Host "ERREUR: Environnement virtuel non trouve" -ForegroundColor Red
    Write-Host ""
    Write-Host "Veuillez d'abord creer et activer l'environnement virtuel :" -ForegroundColor Yellow
    Write-Host "  1. python -m venv .venv" -ForegroundColor Yellow
    Write-Host "  2. .venv\Scripts\activate" -ForegroundColor Yellow
    Write-Host "  3. pip install django cryptography" -ForegroundColor Yellow
    Write-Host "  4. .\init.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "Python detecte : $PYTHON_CMD" -ForegroundColor Cyan

Write-Host "[1/4] Generation SECRET_KEY..." -ForegroundColor Yellow
try {
    $SECRET_KEY = & $PYTHON_CMD -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>&1
    
    # Vérifier si c'est une erreur
    if ($SECRET_KEY -match "Traceback|Error|ModuleNotFoundError") {
        throw "Erreur lors de la generation de SECRET_KEY"
    }
    
    $SECRET_KEY = $SECRET_KEY.Trim()
    
    if ([string]::IsNullOrEmpty($SECRET_KEY)) {
        throw "SECRET_KEY vide"
    }
    
    Write-Host "OK Genere" -ForegroundColor Green
} catch {
    Write-Host "ERREUR: Django n'est pas installe dans l'environnement virtuel" -ForegroundColor Red
    Write-Host "Installez-le avec: pip install django" -ForegroundColor Yellow
    exit 1
}

Write-Host "[2/4] Generation ENCRYPTION_KEY..." -ForegroundColor Yellow
try {
    $ENCRYPTION_KEY = & $PYTHON_CMD -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>&1
    
    # Vérifier si c'est une erreur
    if ($ENCRYPTION_KEY -match "Traceback|Error|ModuleNotFoundError") {
        throw "Erreur lors de la generation de ENCRYPTION_KEY"
    }
    
    $ENCRYPTION_KEY = $ENCRYPTION_KEY.Trim()
    
    if ([string]::IsNullOrEmpty($ENCRYPTION_KEY)) {
        throw "ENCRYPTION_KEY vide"
    }
    
    Write-Host "OK Genere" -ForegroundColor Green
} catch {
    Write-Host "ERREUR: cryptography n'est pas installe dans l'environnement virtuel" -ForegroundColor Red
    Write-Host "Installez-le avec: pip install cryptography" -ForegroundColor Yellow
    exit 1
}

Write-Host "[3/4] Generation JWT_SECRET_KEY..." -ForegroundColor Yellow
try {
    $JWT_SECRET_KEY = & $PYTHON_CMD -c "import secrets; print(secrets.token_urlsafe(64))" 2>&1
    
    # Vérifier si c'est une erreur
    if ($JWT_SECRET_KEY -match "Traceback|Error") {
        throw "Erreur lors de la generation de JWT_SECRET_KEY"
    }
    
    $JWT_SECRET_KEY = $JWT_SECRET_KEY.Trim()
    
    if ([string]::IsNullOrEmpty($JWT_SECRET_KEY)) {
        throw "JWT_SECRET_KEY vide"
    }
    
    Write-Host "OK Genere" -ForegroundColor Green
} catch {
    Write-Host "ERREUR: Impossible de generer JWT_SECRET_KEY" -ForegroundColor Red
    exit 1
}

Write-Host "[4/4] Configuration reCAPTCHA..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Utilisation des cles de TEST Google (publiques, documentees)"
Write-Host "Source: https://developers.google.com/recaptcha/docs/faq"
Write-Host ""

$RECAPTCHA_PUBLIC_KEY = "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
$RECAPTCHA_PRIVATE_KEY = "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"

Write-Host "OK Cles de test Google configurees" -ForegroundColor Green
Write-Host ""

# Créer le contenu du fichier .env
$content = @"
# Genere automatiquement le $(Get-Date -Format "dd-MM-yy HH:mm:ss")
# Tous les secrets sont generes aleatoirement
# reCAPTCHA : cles de test Google (publiques, documentation officielle)

SECRET_KEY=$SECRET_KEY
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

ENCRYPTION_KEY=$ENCRYPTION_KEY
JWT_SECRET_KEY=$JWT_SECRET_KEY

WEBAUTHN_RP_ID=localhost
WEBAUTHN_ORIGIN=http://localhost:8000/

CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080

# Cles reCAPTCHA de TEST (Google)
# Source: https://developers.google.com/recaptcha/docs/faq
RECAPTCHA_PUBLIC_KEY=$RECAPTCHA_PUBLIC_KEY
RECAPTCHA_PRIVATE_KEY=$RECAPTCHA_PRIVATE_KEY
"@

# Écrire dans le fichier
$content | Out-File -FilePath ".env" -Encoding UTF8 -NoNewline

Write-Host ""
Write-Host "[5/5] Generation infrastructure PKI..." -ForegroundColor Yellow
Write-Host ""

# Vérifier si OpenSSL est disponible
$opensslPath = $null

if (Get-Command openssl -ErrorAction SilentlyContinue) {
    $opensslPath = "openssl"
} elseif (Test-Path "C:\Program Files\Git\usr\bin\openssl.exe") {
    $opensslPath = "C:\Program Files\Git\usr\bin\openssl.exe"
} elseif (Test-Path "C:\Git\usr\bin\openssl.exe") {
    $opensslPath = "C:\Git\usr\bin\openssl.exe"
}

if ($opensslPath) {
    if ((Test-Path "pki") -and (Test-Path "pki/doctors/dr-test-fullchain.pem")) {
        Write-Host "OK Infrastructure PKI deja presente" -ForegroundColor Green
    } else {
        Write-Host "Creation Root CA, Intermediate CA et certificat docteur..."
        
        New-Item -ItemType Directory -Path "pki/root-ca" -Force | Out-Null
        New-Item -ItemType Directory -Path "pki/intermediate-ca" -Force | Out-Null
        New-Item -ItemType Directory -Path "pki/doctors" -Force | Out-Null
        New-Item -ItemType Directory -Path "trusted_cas" -Force | Out-Null
        
        & $opensslPath genrsa -out pki/root-ca/root-ca-key.pem 4096 2>$null
        & $opensslPath req -x509 -new -key pki/root-ca/root-ca-key.pem -out pki/root-ca/root-ca-cert.pem -days 3650 -subj "/C=BE/O=Medical Root CA/CN=Root CA" 2>$null
        
        & $opensslPath genrsa -out pki/intermediate-ca/int-key.pem 4096 2>$null
        & $opensslPath req -new -key pki/intermediate-ca/int-key.pem -out pki/intermediate-ca/int-csr.pem -subj "/C=BE/O=CHU Bruxelles/CN=CHU CA" 2>$null
        & $opensslPath x509 -req -in pki/intermediate-ca/int-csr.pem -CA pki/root-ca/root-ca-cert.pem -CAkey pki/root-ca/root-ca-key.pem -CAcreateserial -out pki/intermediate-ca/int-cert.pem -days 1825 2>$null
        
        & $opensslPath genrsa -out pki/doctors/dr-test-key.pem 2048 2>$null
        & $opensslPath req -new -key pki/doctors/dr-test-key.pem -out pki/doctors/dr-test-csr.pem -subj "/C=BE/O=CHU Bruxelles/CN=Dr. Test/emailAddress=test@chu.be" 2>$null
        & $opensslPath x509 -req -in pki/doctors/dr-test-csr.pem -CA pki/intermediate-ca/int-cert.pem -CAkey pki/intermediate-ca/int-key.pem -CAcreateserial -out pki/doctors/dr-test-cert.pem -days 365 2>$null
        
        Get-Content pki/doctors/dr-test-cert.pem, pki/intermediate-ca/int-cert.pem, pki/root-ca/root-ca-cert.pem | Set-Content pki/doctors/dr-test-fullchain.pem
        
        Copy-Item pki/root-ca/root-ca-cert.pem trusted_cas/
        
        Write-Host "OK PKI generee (Root CA + Intermediate CA + Dr. Test)" -ForegroundColor Green
        Write-Host "  Fichier a uploader : pki/doctors/dr-test-fullchain.pem"
    }
} else {
    Write-Host "OpenSSL non trouve - PKI non generee" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path "trusted_cas" -Force | Out-Null
}

Write-Host ""
Write-Host "[6/6] Generation des certificats TLS pour HTTPS..." -ForegroundColor Yellow
Write-Host ""

if ((Test-Path "cert.crt") -and (Test-Path "cert.key")) {
    Write-Host "OK Certificats TLS deja presents" -ForegroundColor Green
} else {
    if ($opensslPath) {
        Write-Host "Creation des certificats TLS auto-signes pour le serveur HTTPS..."
        & $opensslPath req -x509 -newkey rsa:4096 -keyout cert.key -out cert.crt -days 365 -nodes -subj "/C=BE/ST=Brussels/L=Brussels/O=Medical Records/CN=localhost" 2>$null
        Write-Host "OK Certificats TLS generes (valides 1 an)" -ForegroundColor Green
    } else {
        Write-Host "OpenSSL non trouve - Certificats TLS non generes" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  OK Configuration terminee" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Prochaines etapes :"
Write-Host ""
Write-Host "  1. Creer le dossier logs :"
Write-Host "     New-Item -ItemType Directory -Path logs -Force"
Write-Host ""
Write-Host "  2. Appliquer les migrations :"
Write-Host "     python manage.py migrate"
Write-Host ""
Write-Host "  3. Creer un superuser :"
Write-Host "     python manage.py createsuperuser"
Write-Host ""
Write-Host "  4. Lancer le serveur HTTPS :"
Write-Host "     python manage.py runserver_plus --cert-file cert.crt"
Write-Host ""
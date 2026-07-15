# HealthSecure

Secure web platform for managing medical records (Django), featuring authentication
via Keycloak (OIDC), end-to-end encryption of medical files (RSA), a PKI for doctors'
certificates, TLS, CSP + nonces, and an optional ELK logging stack.

## Group members

| Matricule | Name |
|-----------|------|
| 62514     | TO COMPLETE |
| 63649     | TO COMPLETE |

## Requirements

- Docker Desktop (with WSL2 enabled on Windows)
- Python 3.11+ (`python` or `py` available in the PATH)
- OpenSSL (for generating the PKI and TLS certificates)
- Git Bash (bundled with Git for Windows) **or** PowerShell

## Build / Installation

The project provides two equivalent installation scripts that generate the Django
secrets, the PKI, the TLS certificates, start Keycloak (Docker) and automatically
import the realm, then create the `.env` file:

### Ubuntu 22.04 x64 (or Windows 10 x64 via Git Bash)

```bash
chmod +x init.sh
./init.sh
```

### Windows 10 x64 (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File init.ps1
```

The script:
1. Checks the required tools (`docker`, `curl`/`openssl`) and creates a Python virtual environment (`.venv`)
2. Installs the dependencies (`requirements.txt`)
3. Generates `SECRET_KEY`, `ENCRYPTION_KEY`, `JWT_SECRET_KEY`
4. Generates the PKI (Root CA, Intermediate CA, Dr. Test certificate)
5. Generates the TLS certificates (`cert.crt` / `cert.key`)
6. Starts Keycloak (`docker-compose.keycloak.yml`), waits until it is ready, imports the
   `health` realm and retrieves the OIDC client secret for `django-health`
7. Optionally offers to start the ELK stack (`docker-compose.elk.yml`)
8. Generates the `.env` file with all the values above
9. Applies the Django migrations (`manage.py migrate`)

## Usage

Once the installation is complete, activate the venv then run the Django server:

```bash
# Linux / Git Bash
source .venv/bin/activate      # or .venv/Scripts/activate on Windows
python manage.py runserver
```

```powershell
# Windows PowerShell
.venv\Scripts\python.exe manage.py runserver
```

Then open: http://localhost:8000

To run with TLS (self-signed certificate generated during installation):

```bash
python manage.py runserver_plus --cert-file cert.crt
```

### Keycloak access

- Keycloak admin console: http://localhost:8080/admin (`admin` / `admin`)
- Application realm: `health`

### ELK logging stack (optional)

If started during installation:

- Kibana: http://localhost:5601
- Logs are always written to `logs/security.log` and `logs/django.log` regardless of
  whether the ELK stack is running.

### Stopping the Docker services

```bash
docker compose -f docker-compose.keycloak.yml down
docker compose -f docker-compose.elk.yml down   # if the ELK stack was started
```

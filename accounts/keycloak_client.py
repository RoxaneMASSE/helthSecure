import requests
from django.conf import settings

def get_admin_token():
    """Récupère le token admin pour gérer Keycloak."""
    url = f"{settings.KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    resp = requests.post(url, data={
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": settings.KEYCLOAK_ADMIN_USER,
        "password": settings.KEYCLOAK_ADMIN_PASSWORD, 
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]

def create_keycloak_user(first_name, last_name, email, role):
    """Crée un utilisateur SANS mot de passe (WebAuthn ready)."""
    token = get_admin_token()
    realm = settings.KEYCLOAK_REALM
    base = f"{settings.KEYCLOAK_URL}/admin/realms/{realm}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 1. Création de l'utilisateur (SANS credentials)
    payload = {
        "username": email,
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "enabled": True,
        "emailVerified": True,
        "credentials":[],
        "requiredActions": ["webauthn-register"] 
    }

    resp = requests.post(f"{base}/users", json=payload, headers=headers, timeout=10)

    if resp.status_code == 409:
        raise ValueError("Un compte avec cet email existe déjà.")
    
    resp.raise_for_status()

    # 2. Récupération de l'ID utilisateur
    location = resp.headers.get("Location", "")
    user_id = location.rstrip("/").split("/")[-1]

    # 3. Attribution du rôle
    role_resp = requests.get(f"{base}/roles/{role}", headers=headers, timeout=10)
    role_resp.raise_for_status()
    role_data = role_resp.json()

    requests.post(
        f"{base}/users/{user_id}/role-mappings/realm",
        json=[{"id": role_data["id"], "name": role_data["name"]}],
        headers=headers,
        timeout=10,
    ).raise_for_status()

    return user_id

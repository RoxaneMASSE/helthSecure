import requests
from django.conf import settings

def get_admin_token():
    """Retrieves the admin token to manage Keycloak.
    Uses KEYCLOAK_INTERNAL_URL to bypass Nginx (direct port 8180)."""
    url = f"{settings.KEYCLOAK_INTERNAL_URL}/realms/master/protocol/openid-connect/token"
    resp = requests.post(url, data={
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": settings.KEYCLOAK_ADMIN_USER,
        "password": settings.KEYCLOAK_ADMIN_PASSWORD, 
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]

def create_keycloak_user(first_name, last_name, email, role):
    """Creates a user WITHOUT a password (WebAuthn ready).
    Uses KEYCLOAK_INTERNAL_URL to bypass Nginx (direct port 8180)."""
    token = get_admin_token()
    realm = settings.KEYCLOAK_REALM
    base = f"{settings.KEYCLOAK_INTERNAL_URL}/admin/realms/{realm}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 1. Create the user (WITHOUT credentials)
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
        raise ValueError("An account with this email already exists.")
    
    resp.raise_for_status()

    # 2. Retrieve the user ID
    location = resp.headers.get("Location", "")
    user_id = location.rstrip("/").split("/")[-1]

    # 3. Assign the role
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

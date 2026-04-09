import requests
from django.conf import settings


def get_admin_token():
    """Get Keycloak admin token via client credentials."""
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
    """
    Create a user in Keycloak and assign the given role.
    Returns the Keycloak user UUID or raises ValueError with a clean message.
    """
    token = get_admin_token()
    realm = settings.KEYCLOAK_REALM
    base = f"{settings.KEYCLOAK_URL}/admin/realms/{realm}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 1. Create user
    payload = {
    "username": email,
    "email": email,
    "firstName": first_name,
    "lastName": last_name,
    "enabled": True,
    "emailVerified": True,
    # ← plus de "credentials" du tout
    "requiredActions": ["webauthn-register-passwordless"],
    }

    resp = requests.post(f"{base}/users", json=payload, headers=headers, timeout=10)

    if resp.status_code == 409:
        raise ValueError("An account with this email already exists.")

    if resp.status_code == 400:
        # Lire le message d'erreur Keycloak et le traduire proprement
        try:
            error_data = resp.json()
            error_msg = error_data.get("errorMessage", "")
        except Exception:
            error_msg = ""

        # Messages Keycloak → messages lisibles
        password_errors = {
            "invalidPasswordMinLengthMessage":
                "Password must be at least 12 characters long.",
            "invalidPasswordMinDigitsMessage":
                "Password must contain at least 1 number.",
            "invalidPasswordMinUpperCaseMessage":
                "Password must contain at least 1 uppercase letter.",
            "invalidPasswordMinSpecialCharsMessage":
                "Password must contain at least 1 special character (!@#$%...).",
        }

        if error_msg in password_errors:
            raise ValueError(password_errors[error_msg])

        # Message générique si non reconnu
        raise ValueError(
            "Password does not meet security requirements: "
            "at least 12 characters, 1 uppercase, 1 number, 1 special character."
        )

    resp.raise_for_status()

    # 2. Get user UUID from Location header
    location = resp.headers.get("Location", "")
    user_id = location.rstrip("/").split("/")[-1]

    # 3. Get role ID
    role_resp = requests.get(f"{base}/roles/{role}", headers=headers, timeout=10)
    role_resp.raise_for_status()
    role_data = role_resp.json()

    # 4. Assign role
    requests.post(
        f"{base}/users/{user_id}/role-mappings/realm",
        json=[{"id": role_data["id"], "name": role_data["name"]}],
        headers=headers,
        timeout=10,
    ).raise_for_status()

    return user_id
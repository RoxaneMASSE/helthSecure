import jwt
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from accounts.models import UserProfile
from core.models import PatientProfile, DoctorProfile


class KeycloakOIDCBackend(OIDCAuthenticationBackend):

    def _verify_jws(self, token, key):
        headers = jwt.get_unverified_header(token)
        algorithm = headers.get("alg", "RS256")
        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=self.get_settings("OIDC_RP_CLIENT_ID"),
            options={
                "verify_iat": False,
                "verify_exp": True,
                "verify_nbf": True,
            },
        )

    def create_user(self, claims):
        user = super().create_user(claims)
        self._sync_user(user, claims)
        return user

    def update_user(self, user, claims):
        user = super().update_user(user, claims)
        self._sync_user(user, claims)
        return user

    def _sync_user(self, user, claims):
        user.first_name = claims.get("given_name", "")
        user.last_name  = claims.get("family_name", "")
        user.email      = claims.get("email", "")
        user.save()

        roles = claims.get("realm_access", {}).get("roles", [])
        role = "doctor" if "doctor" in roles else "patient"

        UserProfile.objects.get_or_create(user=user)
        UserProfile.objects.filter(user=user).update(
            role=role,
            keycloak_id=claims.get("sub", "")
        )

        if role == "patient":
            PatientProfile.objects.get_or_create(user=user)
        elif role == "doctor":
            DoctorProfile.objects.get_or_create(
                user=user,
                defaults={
                    "first_name": claims.get("given_name", ""),
                    "last_name": claims.get("family_name", ""),
                    "organization": "",
                },
            )
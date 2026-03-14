import time
import jwt
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class KeycloakOIDCBackend(OIDCAuthenticationBackend):
    """
    Backend OIDC étendu pour Keycloak.
    Lit les rôles depuis realm_access.roles et les stocke dans UserProfile.
    """

    def _verify_jws(self, token, key):
        """
        Override pour désactiver la vérification stricte du iat.
        PyJWT rejette les tokens dont le iat est légèrement dans le futur
        à cause du décalage d'horloge entre Windows et Docker.
        """
        headers = jwt.get_unverified_header(token)
        algorithm = headers.get("alg", "RS256")

        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=self.get_settings("OIDC_RP_CLIENT_ID"),
            options={
                "verify_iat": False,  # ignore le décalage d'horloge
                "verify_exp": True,   # garde la vérification d'expiration
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
        role  = "doctor" if "doctor" in roles else "patient"

        from accounts.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role        = role
        profile.keycloak_id = claims.get("sub", "")
        profile.save()
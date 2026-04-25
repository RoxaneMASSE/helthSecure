from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    ROLE_CHOICES = [("doctor", "Médecin"), ("patient", "Patient")]

    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name="userprofile")
    role       = models.CharField(max_length=10, choices=ROLE_CHOICES, default="patient")
    keycloak_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    # Cle publique RSA (format PEM) pour le chiffrement bout en bout.
    public_key = models.TextField(blank=True, null=True)
    # Cle privee RSA chiffree cote client (derivee via KDF puis chiffree).
    encrypted_private_key = models.TextField(blank=True, null=True)
    # Sel de derivation (KDF) utilise cote client.
    key_salt = models.CharField(max_length=255, blank=True, null=True)
    # IV utilise pour le chiffrement symetrique de la cle privee.
    key_iv = models.CharField(max_length=255, blank=True, null=True)

    def str(self):
        return f"{self.user.get_full_name()} ({self.get_role_display()})"

    @property
    def is_doctor(self):
        return self.role == "doctor"

    @property
    def is_patient(self):
        return self.role == "patient"



@receiver(post_save, sender=User)
def create_or_save_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
        # Le PatientProfile n'est cree que si l'utilisateur est un patient.
        # Le role sera mis a jour lors de la premiere connexion OIDC.
        # On ne cree pas de PatientProfile ici car on ne connait pas encore le role.
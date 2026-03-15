from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    ROLE_CHOICES = [("doctor", "Médecin"), ("patient", "Patient")]

    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name="userprofile")
    role       = models.CharField(max_length=10, choices=ROLE_CHOICES, default="patient")
    keycloak_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

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
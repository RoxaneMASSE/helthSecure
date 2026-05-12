from django.contrib.auth.models import User
from django.db import models


class PatientProfile(models.Model):
    # Profil patient: les donnees d'identite restent chiffrees E2E cote client.
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="patient_profile")
    first_name_encrypted = models.TextField(blank=True, null=True)
    last_name_encrypted = models.TextField(blank=True, null=True)
    date_of_birth_encrypted = models.TextField(blank=True, null=True)
    # Medecins autorises a acceder aux donnees de ce patient.
    doctors = models.ManyToManyField(
        User,
        related_name="patients",
        blank=True,
        limit_choices_to={"userprofile__role": "doctor"},
    )
    created_at = models.DateTimeField(auto_now_add=True)


class DoctorProfile(models.Model):
    # Profil medecin (utilisateur de confiance), infos en clair.
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doctor_profile")
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    organization = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class DoctorAppointmentRequest(models.Model):
    # Demande de mise en relation medecin-patient avec workflow d'approbation.
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    doctor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="appointment_requests_sent")
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="appointment_requests_received")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("doctor", "patient")


class MedicalFile(models.Model):
    # Fichier medical chiffre E2E; le serveur ne voit jamais les donnees en clair.
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="medical_files")
    # Contenu binaire du fichier chiffre cote client (AES).
    encrypted_file = models.BinaryField()
    # Metadonnees sensibles chiffrees cote client.
    encrypted_filename = models.TextField()
    encrypted_date = models.TextField()
    # IV utilise pour le chiffrement AES du fichier.
    file_iv = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="uploaded_files")
    # True si le fichier est uploade par un medecin et necessite validation patient.
    requires_approval = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class FileKeyShare(models.Model):
    # Partage de la cle AES d'un fichier, chiffree avec la cle publique RSA du destinataire.
    file = models.ForeignKey(MedicalFile, on_delete=models.CASCADE, related_name="key_shares")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="file_key_shares")
    encrypted_aes_key = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("file", "user")


class FileDeletionRequest(models.Model):
    # Demande de suppression d'un fichier medical, initiee par un medecin, validee par le patient.
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    file = models.ForeignKey(MedicalFile, on_delete=models.CASCADE, related_name="deletion_requests")
    doctor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="deletion_requests_sent")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("file", "doctor")
        
        
class FileModificationRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    file = models.ForeignKey(MedicalFile, on_delete=models.CASCADE, related_name="modification_requests")
    doctor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="modification_requests_sent")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    new_encrypted_file = models.BinaryField()
    new_file_iv = models.CharField(max_length=255)
    new_encrypted_filename = models.TextField()
    new_encrypted_date = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("file", "doctor")
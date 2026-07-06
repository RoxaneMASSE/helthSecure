from django.contrib.auth.models import User
from django.db import models


class PatientProfile(models.Model):
    # Patient profile: identity data stays E2E encrypted client-side.
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="patient_profile")
    first_name_encrypted = models.TextField(blank=True, null=True)
    last_name_encrypted = models.TextField(blank=True, null=True)
    date_of_birth_encrypted = models.TextField(blank=True, null=True)
    # Doctors authorized to access this patient's data.
    doctors = models.ManyToManyField(
        User,
        related_name="patients",
        blank=True,
        limit_choices_to={"userprofile__role": "doctor"},
    )
    created_at = models.DateTimeField(auto_now_add=True)


class DoctorProfile(models.Model):
    # Doctor profile (trusted user), plaintext info.
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doctor_profile")
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    organization = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class DoctorAppointmentRequest(models.Model):
    # Doctor-patient relationship request with approval workflow.
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
    # E2E encrypted medical file; the server never sees the plaintext data.
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="medical_files")
    # Binary content of the file, encrypted client-side (AES).
    encrypted_file = models.BinaryField()
    # Sensitive metadata, encrypted client-side.
    encrypted_filename = models.TextField()
    encrypted_date = models.TextField()
    # IV used for AES encryption of the file.
    file_iv = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="uploaded_files")
    # True if the file was uploaded by a doctor and requires patient validation.
    requires_approval = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class FileKeyShare(models.Model):
    # Share of a file's AES key, encrypted with the recipient's RSA public key.
    file = models.ForeignKey(MedicalFile, on_delete=models.CASCADE, related_name="key_shares")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="file_key_shares")
    encrypted_aes_key = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("file", "user")


class FileDeletionRequest(models.Model):
    # Request to delete a medical file, initiated by a doctor, validated by the patient.
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
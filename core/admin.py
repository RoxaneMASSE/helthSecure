from django.contrib import admin
from .models import PatientProfile, DoctorProfile, DoctorAppointmentRequest, MedicalFile, FileKeyShare


@admin.register(MedicalFile)
class MedicalFileAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "uploaded_by", "requires_approval", "approved", "created_at")
    readonly_fields = ("encrypted_filename", "encrypted_date", "file_iv", "encrypted_file")


@admin.register(FileKeyShare)
class FileKeyShareAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "user", "created_at")
    readonly_fields = ("encrypted_aes_key",)


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "first_name", "last_name", "organization")


@admin.register(DoctorAppointmentRequest)
class DoctorAppointmentRequestAdmin(admin.ModelAdmin):
    list_display = ("doctor", "patient", "status", "created_at")

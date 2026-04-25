from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "keycloak_id")
    readonly_fields = ("public_key", "encrypted_private_key", "key_salt", "key_iv")

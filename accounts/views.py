import json
import base64

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login as django_login
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from urllib.parse import urlencode
from django.views.decorators.cache import never_cache
from django_ratelimit.decorators import ratelimit

from .forms import PatientRegistrationForm, DoctorRegistrationForm
from .keycloak_client import create_keycloak_user
from .certificate import certificate_service
from .models import UserProfile



# ── Registration (Keycloak) ───────────────────────────────────────────────────

@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def register(request):
    """Single registration page with role selector."""
    role = request.GET.get("role", "patient")

    if request.method == "POST":
        role = request.POST.get("role", "patient")

        if role == "patient":
            form = PatientRegistrationForm(request.POST)
            if form.is_valid():
                try:
                    create_keycloak_user(
                        first_name=form.cleaned_data["first_name"],
                        last_name=form.cleaned_data["last_name"],
                        email=form.cleaned_data["email"],
                        role="patient",
                    )
                    messages.success(request, "Account created! You can now log in.")
                    return redirect("/oidc/authenticate/")
                except ValueError as e:
                    form.add_error(None, str(e))
                except Exception as e:
                    form.add_error(None, f"Registration failed: {e}")

        elif role == "doctor":
            form = DoctorRegistrationForm(request.POST, request.FILES)
            if form.is_valid():
                cert_file = request.FILES.get("certificate")
                if not cert_file:
                    form.add_error("certificate", "Please upload your certificate.")
                else:
                    try:
                        cert_info = certificate_service.validate_certificate_chain(
                            cert_file=cert_file,
                            user_email=form.cleaned_data["email"],
                            ip_address=request.META.get("REMOTE_ADDR"),
                        )
                        create_keycloak_user(
                            first_name=form.cleaned_data["first_name"],
                            last_name=form.cleaned_data["last_name"],
                            email=form.cleaned_data["email"],
                            role="doctor",
                        )
                        messages.success(
                            request,
                            f"Doctor account created for {cert_info['subject']} "
                            f"({cert_info['organization']}). You can now log in."
                        )
                        return redirect("/oidc/authenticate/")
                    except ValidationError as e:
                        form.add_error("certificate", e.message)
                    except ValueError as e:
                        form.add_error(None, str(e))
                    except Exception as e:
                        form.add_error(None, f"Registration failed: {e}")

        else:
            form = PatientRegistrationForm()

    else:
        form = PatientRegistrationForm() if role == "patient" else DoctorRegistrationForm()

    return render(request, "accounts/register.html", {"form": form, "role": role})




@login_required
@never_cache
def profil(request):
    try:
        profile = request.user.userprofile
    except Exception:
        profile = None
    return render(request, "accounts/profil.html", {"profile": profile})


def acces_refuse(request):
    return render(request, "accounts/acces_refuse.html", status=403)

from django.contrib.auth import logout as django_logout

def logout_view(request):
    # 1. Retrieve the ID token before clearing the session
    id_token = request.session.get('oidc_id_token')

    # 2. Log out of Django
    django_logout(request)

    # 3. Build the Keycloak logout URL
    endpoint = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/logout"

    params = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        "post_logout_redirect_uri": "http://localhost:8000/", # Must match EXACTLY what is configured in Keycloak
    }

    if id_token:
        params["id_token_hint"] = id_token

    return redirect(f"{endpoint}?{urlencode(params)}")


# ── E2E RSA key management ────────────────────────────────────────────────────

@login_required
@never_cache
def setup_keys(request):
    """RSA key generation page (first login, no key configured yet)."""
    try:
        profile = request.user.userprofile
        # If keys are already configured, go back to the normal flow
        if profile.public_key:
            return redirect("/")
    except Exception:
        pass
    return render(request, "accounts/setup_keys.html")


@login_required
@never_cache
def unlock_keys(request):
    """RSA key unlock page (subsequent logins)."""
    try:
        profile = request.user.userprofile
        # If no key is configured, redirect to setup
        if not profile.public_key:
            return redirect("accounts:setup_keys")
    except Exception:
        return redirect("accounts:setup_keys")
    return render(request, "accounts/unlock_keys.html")


@login_required
@require_POST
def api_store_keys(request):
    """API: stores the encrypted RSA keys in UserProfile (initial generation)."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    public_key = data.get("public_key", "").strip()
    encrypted_private_key = data.get("encrypted_private_key", "").strip()
    key_salt = data.get("key_salt", "").strip()
    key_iv = data.get("key_iv", "").strip()

    if not all([public_key, encrypted_private_key, key_salt, key_iv]):
        return JsonResponse({"success": False, "error": "Missing data."}, status=400)

    try:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.public_key = public_key
        profile.encrypted_private_key = encrypted_private_key
        profile.key_salt = key_salt
        profile.key_iv = key_iv
        profile.save(update_fields=["public_key", "encrypted_private_key", "key_salt", "key_iv"])
        # Mark the keys as unlocked for this session
        request.session["keys_unlocked"] = True
        return JsonResponse({"success": True})
    except Exception:
        return JsonResponse({"success": False, "error": "Error while storing keys."}, status=500)


@login_required
def api_get_keys(request):
    """API: returns the encrypted data needed for client-side unlocking."""
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Method not allowed."}, status=405)
    try:
        profile = request.user.userprofile
        if not profile.encrypted_private_key:
            return JsonResponse({"success": False, "error": "No key configured."}, status=404)
        return JsonResponse({
            "success": True,
            "encrypted_private_key": profile.encrypted_private_key,
            "key_salt": profile.key_salt,
            "key_iv": profile.key_iv,
        })
    except Exception:
        return JsonResponse({"success": False, "error": "Profile not found."}, status=404)


@login_required
@require_POST
def api_mark_unlocked(request):
    """API: marks the keys as unlocked for the current session."""
    request.session["keys_unlocked"] = True
    return JsonResponse({"success": True})

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

from webauthn.helpers.structs import PublicKeyCredentialDescriptor


import webauthn
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

from .forms import PatientRegistrationForm, DoctorRegistrationForm
from .keycloak_client import create_keycloak_user
from .certificate import certificate_service



# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_rp_id():
    return settings.WEBAUTHN_RP_ID

def _get_origin():
    return settings.WEBAUTHN_ORIGIN.rstrip('/')

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
                        return render(request, 'accounts/acces_refuse.html', {'message': 'Compte créé, veuillez vous connecter.'})
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
    # 1. Récupérer l'ID Token avant de vider la session
    id_token = request.session.get('oidc_id_token')
    
    # 2. Déconnexion de Django
    django_logout(request)
    
    # 3. Construire l'URL de logout Keycloak
    endpoint = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/logout"
    
    params = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        "post_logout_redirect_uri": "http://localhost:8000/", # Doit correspondre EXACTEMENT à Keycloak
    }
    
    if id_token:
        params["id_token_hint"] = id_token
        
    return redirect(f"{endpoint}?{urlencode(params)}")
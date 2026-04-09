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
from .models import WebAuthnCredential


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
                    user, created = User.objects.get_or_create(
                        username=form.cleaned_data["email"],
                        defaults={
                            "email": form.cleaned_data["email"],
                            "first_name": form.cleaned_data["first_name"],
                            "last_name": form.cleaned_data["last_name"],
                        }
                    )
                    django_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    messages.success(request, "Account created! Now register your passkey.")
                    return redirect("accounts:webauthn_register_begin_page")
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
                        user, created = User.objects.get_or_create(
                            username=form.cleaned_data["email"],
                            defaults={
                                "email": form.cleaned_data["email"],
                                "first_name": form.cleaned_data["first_name"],
                                "last_name": form.cleaned_data["last_name"],
                            }
                        )
                        django_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                        messages.success(request, f"Doctor account created for {cert_info['subject']}.")
                        return redirect("accounts:webauthn_register_begin_page")
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


# ── WebAuthn — enregistrement ─────────────────────────────────────────────────

@login_required
def webauthn_register_begin(request):
    user = request.user

    options = webauthn.generate_registration_options(
        rp_id=_get_rp_id(),
        rp_name="HealthSecure",
        user_id=str(user.id).encode(),
        user_name=user.username,
        user_display_name=user.get_full_name() or user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED,
            resident_key=ResidentKeyRequirement.PREFERRED,
        ),
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
    )

    request.session['webauthn_register_challenge'] = base64.b64encode(
        options.challenge
    ).decode()

    return JsonResponse(json.loads(webauthn.options_to_json(options)))


@login_required
@require_POST
def webauthn_register_complete(request):
    try:
        challenge_b64 = request.session.get('webauthn_register_challenge')
        if not challenge_b64:
            return JsonResponse({'error': 'No challenge in session'}, status=400)

        challenge = base64.b64decode(challenge_b64)
        body = json.loads(request.body)

        verification = webauthn.verify_registration_response(
            credential=body,
            expected_challenge=challenge,
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
            require_user_verification=True,
        )

        WebAuthnCredential.objects.create(
            user=request.user,
            credential_id=verification.credential_id,
            public_key=verification.credential_public_key,
            sign_count=verification.sign_count,
        )

        del request.session['webauthn_register_challenge']
        return JsonResponse({'status': 'ok'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ── WebAuthn — login ──────────────────────────────────────────────────────────

def webauthn_login_page(request):
    return render(request, "accounts/webauthn_login.html")


@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def webauthn_login_begin(request):
    try:
        body = json.loads(request.body)
        username = body.get('username', '').strip()

        if not username:
            return JsonResponse({'error': 'Email required'}, status=400)

        try:
            user = User.objects.get(email__iexact=username)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)

        credentials = WebAuthnCredential.objects.filter(user=user)
        if not credentials.exists():
            return JsonResponse({'error': 'No WebAuthn credential registered'}, status=404)

        allow_credentials = [
            PublicKeyCredentialDescriptor(id=bytes(cred.credential_id))
            for cred in credentials
        ]

        options = webauthn.generate_authentication_options(
            rp_id=_get_rp_id(),
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        request.session['webauthn_login_challenge'] = base64.b64encode(
            options.challenge
        ).decode()
        request.session['webauthn_login_username'] = user.email

        return JsonResponse(json.loads(webauthn.options_to_json(options)))

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_POST
def webauthn_login_complete(request):
    try:
        challenge_b64 = request.session.get('webauthn_login_challenge')
        username = request.session.get('webauthn_login_username')

        if not challenge_b64 or not username:
            return JsonResponse({'error': 'No challenge in session'}, status=400)

        challenge = base64.b64decode(challenge_b64)
        body = json.loads(request.body)
        user = User.objects.get(email__iexact=username)

        credential_id_bytes = base64.urlsafe_b64decode(body['id'] + '==')
        cred = WebAuthnCredential.objects.get(
            user=user,
            credential_id=credential_id_bytes,
        )

        verification = webauthn.verify_authentication_response(
            credential=body,
            expected_challenge=challenge,
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
            credential_public_key=bytes(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )

        cred.sign_count = verification.new_sign_count
        cred.save()

        del request.session['webauthn_login_challenge']
        del request.session['webauthn_login_username']

        django_login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        return JsonResponse({'status': 'ok', 'redirect': '/'})

    except WebAuthnCredential.DoesNotExist:
        return JsonResponse({'error': 'Credential not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


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
    id_token = request.session.get('oidc_id_token')
    django_logout(request)

    endpoint = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/logout"
    params = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        "post_logout_redirect_uri": "http://localhost:8000/",
    }
    if id_token:
        params["id_token_hint"] = id_token

    return redirect(f"{endpoint}?{urlencode(params)}")


@login_required
def webauthn_register_page(request):
    return render(request, "accounts/webauthn_setup.html")
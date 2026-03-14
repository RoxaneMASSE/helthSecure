from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError

from .forms import PatientRegistrationForm, DoctorRegistrationForm
from .keycloak_client import create_keycloak_user
from .certificate import certificate_service


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
                        password=form.cleaned_data["password"],
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
                            password=form.cleaned_data["password"],
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
def profil(request):
    try:
        profile = request.user.userprofile
    except Exception:
        profile = None
    return render(request, "accounts/profil.html", {"profile": profile})


def acces_refuse(request):
    return render(request, "accounts/acces_refuse.html", status=403)
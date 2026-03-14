from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required


def home(request):
    if request.user.is_authenticated:
        try:
            role = request.user.userprofile.role
            return redirect("core:dashboard_doctor" if role == "doctor" else "core:dashboard_patient")
        except Exception:
            pass
    return render(request, "core/home.html")


@login_required
@role_required("doctor")
def dashboard_doctor(request):
    return render(request, "core/dashboard_doctor.html")


@login_required
@role_required("patient")
def dashboard_patient(request):
    return render(request, "core/dashboard_patient.html")
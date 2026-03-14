from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/doctor/",  views.dashboard_doctor,  name="dashboard_doctor"),
    path("dashboard/patient/", views.dashboard_patient, name="dashboard_patient"),
]
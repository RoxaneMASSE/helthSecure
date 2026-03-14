from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("profil/", views.profil, name="profil"),
    path("acces-refuse/", views.acces_refuse, name="acces_refuse"),
]
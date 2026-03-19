from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("profil/", views.profil, name="profil"),
    path("acces-refuse/", views.acces_refuse, name="acces_refuse"),
    path("logout/", views.logout_view, name="logout"),
    
    # WebAuthn
    path("webauthn/register/begin/",     views.webauthn_register_begin,   name="webauthn_register_begin"),
    path("webauthn/register/complete/",  views.webauthn_register_complete,name="webauthn_register_complete"),
    path("webauthn/login/begin/",        views.webauthn_login_begin,      name="webauthn_login_begin"),
    path("webauthn/login/complete/",     views.webauthn_login_complete,   name="webauthn_login_complete"),
    path("webauthn/login/",              views.webauthn_login_page,       name="webauthn_login"),

]
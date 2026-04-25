from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("profil/", views.profil, name="profil"),
    path("acces-refuse/", views.acces_refuse, name="acces_refuse"),
    path("logout/", views.logout_view, name="logout"),
    # Gestion des clés RSA E2E
    path("setup-keys/", views.setup_keys, name="setup_keys"),
    path("unlock-keys/", views.unlock_keys, name="unlock_keys"),
    path("api/store-keys/", views.api_store_keys, name="api_store_keys"),
    path("api/get-keys/", views.api_get_keys, name="api_get_keys"),
    path("api/mark-unlocked/", views.api_mark_unlocked, name="api_mark_unlocked"),
]
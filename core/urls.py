from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/doctor/",  views.dashboard_doctor,  name="dashboard_doctor"),
    path("dashboard/patient/", views.dashboard_patient, name="dashboard_patient"),
    path("doctors/", views.my_doctors, name="my_doctors"),
    path("doctors/add/", views.add_doctor, name="add_doctor"),
    path("doctors/remove/<int:doctor_id>/", views.remove_doctor, name="remove_doctor"),
    path("doctors/request/<int:request_id>/<str:action>/", views.handle_request, name="handle_request"),
    path("doctors/search/", views.search_doctors, name="search_doctors"),
    path("patients/", views.my_patients, name="my_patients"),
    path("patients/request/", views.request_patient, name="request_patient"),
    path("patients/search/", views.search_patients, name="search_patients"),
    # Fichiers medicaux E2E
    path("files/", views.medical_files, name="medical_files"),
    path("files/upload/", views.upload_file, name="upload_file"),
    path("files/download/<int:file_id>/", views.download_file, name="download_file"),
    path("files/delete/<int:file_id>/", views.delete_file, name="delete_file"),
    path("files/approve/<int:file_id>/", views.approve_file, name="approve_file"),
    path("files/api/doctors-keys/", views.api_patient_doctors_keys, name="api_patient_doctors_keys"),
    path("files/patient/<int:patient_id>/", views.doctor_patient_files, name="doctor_patient_files"),
    path("files/patient/<int:patient_id>/upload/", views.doctor_upload_file, name="doctor_upload_file"),
    path("files/patient/<int:patient_id>/keys/", views.api_doctor_patient_keys, name="api_doctor_patient_keys"),
    # API re-chiffrement lors de l'ajout d'un medecin
    path("api/user-public-key/<int:user_id>/", views.api_user_public_key, name="api_user_public_key"),
    path("api/my-file-keys/", views.api_my_file_keys, name="api_my_file_keys"),
    path("api/add-file-key-shares/", views.api_add_file_key_shares, name="api_add_file_key_shares"),
]
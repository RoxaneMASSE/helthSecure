import base64
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from accounts.decorators import role_required
from .models import DoctorAppointmentRequest, DoctorProfile, FileDeletionRequest, FileKeyShare, MedicalFile, FileModificationRequest

def home(request):
    if request.user.is_authenticated:
        try:
            # Vider le cache du profil pour relire depuis la BDD
            if hasattr(request.user, '_userprofile_cache'):
                del request.user._userprofile_cache
            from accounts.models import UserProfile
            profile = UserProfile.objects.get(user=request.user)

            # Étape 1 : si les clés RSA E2E ne sont pas encore générées → setup
            if not profile.public_key:
                return redirect("accounts:setup_keys")

            # Étape 2 : si les clés ne sont pas déverrouillées pour cette session → unlock
            if not request.session.get("keys_unlocked"):
                return redirect("accounts:unlock_keys")

            # Étape 3 : rediriger vers le bon dashboard selon le rôle
            role = profile.role
            return redirect("core:dashboard_doctor" if role == "doctor" else "core:dashboard_patient")
        except Exception:
            pass
    return render(request, "core/home.html")


@login_required
@role_required("doctor")
def dashboard_doctor(request):
    sent_requests = DoctorAppointmentRequest.objects.filter(doctor=request.user).select_related("patient")
    patients = request.user.patients.select_related("patient_profile").all()
    context = {
        "patients": patients,
        "sent_requests": sent_requests,
        "sent_requests_pending_count": sent_requests.filter(status=DoctorAppointmentRequest.STATUS_PENDING).count(),
    }
    return render(request, "core/dashboard_doctor.html", context)


@login_required
@role_required("patient")
def dashboard_patient(request):
    pending_requests = DoctorAppointmentRequest.objects.filter(
        patient=request.user,
        status=DoctorAppointmentRequest.STATUS_PENDING,
    ).select_related("doctor__doctor_profile")
    doctors = request.user.patient_profile.doctors.select_related("doctor_profile").all()
    context = {
        "doctors": doctors,
        "pending_requests": pending_requests,
        "pending_requests_count": pending_requests.count(),
    }
    return render(request, "core/dashboard_patient.html", context)


@login_required
@role_required("patient")
def my_doctors(request):
    # Liste des medecins du patient + demandes recues en attente.
    doctors = request.user.patient_profile.doctors.select_related("doctor_profile").all()
    pending_requests = DoctorAppointmentRequest.objects.filter(
        patient=request.user,
        status=DoctorAppointmentRequest.STATUS_PENDING,
    ).select_related("doctor__doctor_profile")
    context = {
        "doctors": doctors,
        "pending_requests": pending_requests,
    }
    return render(request, "core/my_doctors.html", context)


@login_required
@role_required("patient")
@require_POST
def add_doctor(request):
    # Ajout direct d'un medecin a la liste du patient.
    doctor_id = request.POST.get("doctor_id")
    if not doctor_id:
        messages.error(request, "Medecin invalide.")
        return redirect("core:my_doctors")

    doctor = get_object_or_404(
        User.objects.select_related("userprofile", "doctor_profile"),
        id=doctor_id,
        userprofile__role="doctor",
    )
    patient_profile = request.user.patient_profile
    if patient_profile.doctors.filter(id=doctor.id).exists():
        messages.info(request, "Ce medecin est deja associe.")
        return redirect("core:my_doctors")

    patient_profile.doctors.add(doctor)
    DoctorAppointmentRequest.objects.filter(doctor=doctor, patient=request.user).update(
        status=DoctorAppointmentRequest.STATUS_APPROVED
    )
    messages.success(request, "Medecin ajoute avec succes.")
    return redirect("core:my_doctors")


@login_required
@role_required("patient")
@require_POST
def remove_doctor(request, doctor_id):
    # Retrait du medecin + suppression des partages de cles sur les fichiers du patient.
    patient_profile = request.user.patient_profile
    doctor = get_object_or_404(User, id=doctor_id, userprofile__role="doctor")

    if not patient_profile.doctors.filter(id=doctor.id).exists():
        messages.error(request, "Ce medecin n'est pas associe a votre profil.")
        return redirect("core:my_doctors")

    patient_profile.doctors.remove(doctor)
    FileKeyShare.objects.filter(file__patient=request.user, user=doctor).delete()
    DoctorAppointmentRequest.objects.filter(doctor=doctor, patient=request.user).update(
        status=DoctorAppointmentRequest.STATUS_REJECTED
    )
    messages.success(request, "Medecin retire et acces aux cles supprime.")
    return redirect("core:my_doctors")


@login_required
@role_required("patient")
@require_POST
def handle_request(request, request_id, action):
    # Approbation/rejet d'une demande de suivi de patient.
    appointment_request = get_object_or_404(DoctorAppointmentRequest, id=request_id, patient=request.user)
    if appointment_request.status != DoctorAppointmentRequest.STATUS_PENDING:
        messages.error(request, "Cette demande a deja ete traitee.")
        return redirect("core:my_doctors")

    if action == "approve":
        request.user.patient_profile.doctors.add(appointment_request.doctor)
        appointment_request.status = DoctorAppointmentRequest.STATUS_APPROVED
        appointment_request.save(update_fields=["status", "updated_at"])
        messages.success(request, "Demande approuvee.")
    elif action == "reject":
        appointment_request.status = DoctorAppointmentRequest.STATUS_REJECTED
        appointment_request.save(update_fields=["status", "updated_at"])
        messages.info(request, "Demande rejetee.")
    else:
        messages.error(request, "Action invalide.")

    return redirect("core:my_doctors")


@login_required
@role_required("patient")
@require_GET
@ratelimit(key="user_or_ip", rate="20/m", method="GET", block=True)
def search_doctors(request):
    # Recherche des medecins par nom/prenom.
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    doctors = (
        DoctorProfile.objects.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query))
        .select_related("user")
        .distinct()[:10]
    )

    return JsonResponse(
        {
            "results": [
                {
                    "id": doctor.user.id,
                    "full_name": f"Dr. {doctor.first_name} {doctor.last_name}",
                    "organization": doctor.organization,
                }
                for doctor in doctors
            ]
        }
    )


@login_required
@role_required("doctor")
def my_patients(request):
    # Liste des patients suivis + demandes envoyees.
    # Note: request.user.patients = M2M vers User (patients suivis par ce doctor)
    # On recupere les PatientProfile associes via l'utilisateur patient
    patients = request.user.patients.all()
    sent_requests = DoctorAppointmentRequest.objects.filter(doctor=request.user).select_related("patient")
    context = {
        "patients": patients,
        "sent_requests": sent_requests,
    }
    return render(request, "core/my_patients.html", context)


@login_required
@role_required("doctor")
@require_POST
def request_patient(request):
    # Envoi d'une demande pour suivre un patient.
    patient_id = request.POST.get("patient_id")
    if not patient_id:
        messages.error(request, "Patient invalide.")
        return redirect("core:my_patients")

    patient = get_object_or_404(User.objects.select_related("userprofile"), id=patient_id, userprofile__role="patient")
    if request.user.patients.filter(id=patient.id).exists():
        messages.info(request, "Vous suivez deja ce patient.")
        return redirect("core:my_patients")

    appointment_request, created = DoctorAppointmentRequest.objects.get_or_create(
        doctor=request.user,
        patient=patient,
        defaults={"status": DoctorAppointmentRequest.STATUS_PENDING},
    )
    if created:
        messages.success(request, "Demande envoyee au patient.")
    elif appointment_request.status == DoctorAppointmentRequest.STATUS_REJECTED:
        appointment_request.status = DoctorAppointmentRequest.STATUS_PENDING
        appointment_request.save(update_fields=["status", "updated_at"])
        messages.success(request, "Demande renvoyee au patient.")
    elif appointment_request.status == DoctorAppointmentRequest.STATUS_PENDING:
        messages.info(request, "Une demande est deja en attente pour ce patient.")
    else:
        messages.info(request, "Vous suivez deja ce patient.")

    return redirect("core:my_patients")


@login_required
@role_required("doctor")
@require_GET
@ratelimit(key="user_or_ip", rate="20/m", method="GET", block=True)
def search_patients(request):
    # Recherche des patients par username OU email.
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    # Chercher dans username ou email, et verifier que c'est bien un patient
    patients = User.objects.filter(
        userprofile__role="patient"
    ).filter(
        Q(username__icontains=query) | Q(email__icontains=query)
    ).exclude(id=request.user.id)[:10]
    
    return JsonResponse(
        {
            "results": [
                {
                    "id": patient.id,
                    "username": patient.username,
                    "email": patient.email,
                }
                for patient in patients
            ]
        }
    )


# ── Fichiers medicaux E2E ─────────────────────────────────────────────────────

@login_required
@role_required("patient")
def medical_files(request):
    """Page principale: liste des fichiers medicaux chiffres du patient."""
    files = (
        MedicalFile.objects
        .filter(patient=request.user)
        .prefetch_related("key_shares")
        .order_by("-created_at")
    )
    files_data = []
    for f in files:
        ks = f.key_shares.filter(user=request.user).first()
        files_data.append({
            "id": f.id,
            "encrypted_filename": f.encrypted_filename,
            "encrypted_date": f.encrypted_date,
            "file_iv": f.file_iv,
            "encrypted_aes_key": ks.encrypted_aes_key if ks else None,
            "requires_approval": f.requires_approval,
            "approved": f.approved,
        })

    # Demandes de suppression en attente pour les fichiers de ce patient
    pending_deletion_requests = (
        FileDeletionRequest.objects
        .filter(file__patient=request.user, status=FileDeletionRequest.STATUS_PENDING)
        .select_related("doctor__doctor_profile", "file")
    )
    deletion_requests_data = []
    for dr in pending_deletion_requests:
        doctor_name = (
            f"Dr. {dr.doctor.doctor_profile.first_name} {dr.doctor.doctor_profile.last_name}"
            if hasattr(dr.doctor, "doctor_profile") else dr.doctor.username
        )
        deletion_requests_data.append({
            "id": dr.id,
            "file_id": dr.file_id,
            "doctor_name": doctor_name,
        })

    # Demandes de modification en attente
    pending_modification_requests = (
        FileModificationRequest.objects
        .filter(file__patient=request.user, status=FileModificationRequest.STATUS_PENDING)
        .select_related("doctor__doctor_profile", "file")
    )
    modification_requests_data = []
    for mr in pending_modification_requests:
        doctor_name = (
            f"Dr. {mr.doctor.doctor_profile.first_name} {mr.doctor.doctor_profile.last_name}"
            if hasattr(mr.doctor, "doctor_profile") else mr.doctor.username
        )
        modification_requests_data.append({
            "id": mr.id,
            "file_id": mr.file_id,
            "doctor_name": doctor_name,
            "new_encrypted_filename": mr.new_encrypted_filename,
            "new_encrypted_date": mr.new_encrypted_date,
            "new_file_iv": mr.new_file_iv,
            # Note : le nouveau fichier chiffré n'est pas transmis ici,
            # il sera récupéré au moment de l'approbation côté serveur.
        })

    return render(request, "core/medical_files.html", {
        "files_data_json": json.dumps(files_data),
        "deletion_requests_json": json.dumps(deletion_requests_data),
        "modification_requests_json": json.dumps(modification_requests_data),
    })


@login_required
@role_required("patient")
@require_POST
def upload_file(request):
    """Recoit les donnees chiffrees E2E et stocke le fichier medical."""
    try:
        data = json.loads(request.body)
        encrypted_file_b64 = data["encrypted_file"]
        encrypted_filename = data["encrypted_filename"]
        encrypted_date = data["encrypted_date"]
        file_iv = data["file_iv"]
        key_shares = data["key_shares"]

        encrypted_file_bytes = base64.b64decode(encrypted_file_b64)
        if len(encrypted_file_bytes) > 10 * 1024 * 1024:
            return JsonResponse({"error": "Fichier trop volumineux (max 10 MB)."}, status=400)

        medical_file = MedicalFile.objects.create(
            patient=request.user,
            encrypted_file=encrypted_file_bytes,
            encrypted_filename=encrypted_filename,
            encrypted_date=encrypted_date,
            file_iv=file_iv,
            uploaded_by=request.user,
            requires_approval=False,
            approved=True,
        )
        for ks_data in key_shares:
            user = User.objects.get(id=ks_data["user_id"])
            FileKeyShare.objects.create(
                file=medical_file,
                user=user,
                encrypted_aes_key=ks_data["encrypted_aes_key"],
            )
        return JsonResponse({"success": True, "file_id": medical_file.id})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def download_file(request, file_id):
    """Retourne le fichier chiffre et la cle AES chiffree pour l'utilisateur connecte."""
    medical_file = get_object_or_404(MedicalFile, id=file_id)

    # Bloquer le telechargement si le fichier necessite une approbation non encore accordee
    if medical_file.requires_approval and not medical_file.approved:
        return JsonResponse({"error": "Ce fichier n'a pas encore ete approuve par le patient."}, status=403)

    # Verifier que l'utilisateur est le patient OU un medecin associe
    is_patient = (medical_file.patient_id == request.user.id)
    is_doctor = False
    try:
        is_doctor = medical_file.patient.patient_profile.doctors.filter(
            id=request.user.id
        ).exists()
    except Exception:
        pass

    if not (is_patient or is_doctor):
        return JsonResponse({"error": "Acces refuse."}, status=403)

    ks = get_object_or_404(FileKeyShare, file=medical_file, user=request.user)
    # Encoder le contenu binaire en base64 pour le transport JSON
    encrypted_file_b64 = base64.b64encode(bytes(medical_file.encrypted_file)).decode()
    return JsonResponse({
        "encrypted_file": encrypted_file_b64,
        "file_iv": medical_file.file_iv,
        "encrypted_filename": medical_file.encrypted_filename,
        "encrypted_aes_key": ks.encrypted_aes_key,
    })


@login_required
@role_required("patient")
@require_POST
def approve_file(request, file_id):
    """Approbation ou rejet d'un fichier medical uploade par un medecin.
    Seul le patient proprietaire du fichier peut approuver ou rejeter."""
    medical_file = get_object_or_404(MedicalFile, id=file_id, patient=request.user)

    # Verifier que le fichier necessite bien une approbation
    if not medical_file.requires_approval:
        return JsonResponse({"error": "Ce fichier ne necessite pas d'approbation."}, status=400)

    action = request.POST.get("action")

    if action == "approve":
        # Marquer le fichier comme approuve
        medical_file.approved = True
        medical_file.save(update_fields=["approved"])
        return JsonResponse({"success": True, "action": "approved"})

    elif action == "reject":
        # Supprimer le fichier et tous ses partages de cles
        medical_file.delete()
        return JsonResponse({"success": True, "action": "rejected"})

    else:
        return JsonResponse({"error": "Action invalide. Utilisez 'approve' ou 'reject'."}, status=400)


@login_required
@role_required("patient")
@require_POST
def delete_file(request, file_id):
    """Supprime un fichier medical et tous ses partages de cles."""
    medical_file = get_object_or_404(MedicalFile, id=file_id, patient=request.user)
    medical_file.delete()
    return JsonResponse({"success": True})


@login_required
@role_required("patient")
@require_GET
def api_patient_doctors_keys(request):
    """Retourne la cle publique du patient et de ses medecins associes."""
    patient_public_key = None
    try:
        patient_public_key = request.user.userprofile.public_key
    except Exception:
        pass

    doctors_list = []
    try:
        for doctor in request.user.patient_profile.doctors.select_related("userprofile").all():
            try:
                pub_key = doctor.userprofile.public_key
                if pub_key:
                    doctors_list.append({
                        "user_id": doctor.id,
                        "public_key": pub_key,
                    })
            except Exception:
                pass
    except Exception:
        pass

    return JsonResponse({
        "patient": {
            "user_id": request.user.id,
            "public_key": patient_public_key,
        },
        "doctors": doctors_list,
    })


@login_required
@role_required("doctor")
def doctor_patient_files(request, patient_id):
    """Affiche les fichiers medicaux d'un patient pour le medecin associe."""
    patient = get_object_or_404(User, id=patient_id, userprofile__role="patient")
    # Verifier que le medecin est associe au patient
    try:
        is_associated = patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        messages.error(request, "Vous n'etes pas associe a ce patient.")
        return redirect("core:my_patients")

    files = (
        MedicalFile.objects
        .filter(patient=patient)
        .prefetch_related("key_shares")
        .order_by("-created_at")
    )
    files_data = []
    for f in files:
        ks = f.key_shares.filter(user=request.user).first()
        # Verifier s'il y a deja une demande de suppression en attente par CE medecin
        pending_del = f.deletion_requests.filter(
            doctor=request.user, status=FileDeletionRequest.STATUS_PENDING
        ).exists()
        
        pending_mod = f.modification_requests.filter(
            doctor=request.user, status=FileModificationRequest.STATUS_PENDING
        ).exists()
        
        files_data.append({
            "id": f.id,
            "encrypted_filename": f.encrypted_filename,
            "encrypted_date": f.encrypted_date,
            "file_iv": f.file_iv,
            "encrypted_aes_key": ks.encrypted_aes_key if ks else None,
            "requires_approval": f.requires_approval,
            "approved": f.approved,
            "deletion_pending": pending_del,
            "modification_pending": pending_mod,
        })
    return render(request, "core/doctor_patient_files.html", {
        "patient": patient,
        "files_data_json": json.dumps(files_data),
        "patient_id": patient_id,
    })


@login_required
@role_required("doctor")
@require_POST
def doctor_upload_file(request, patient_id):
    """Upload d'un fichier par un medecin pour un patient. Necessite validation patient."""
    patient = get_object_or_404(User, id=patient_id, userprofile__role="patient")
    try:
        is_associated = patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        return JsonResponse({"error": "Acces refuse."}, status=403)

    try:
        data = json.loads(request.body)
        encrypted_file_b64 = data["encrypted_file"]
        encrypted_filename = data["encrypted_filename"]
        encrypted_date = data["encrypted_date"]
        file_iv = data["file_iv"]
        key_shares = data["key_shares"]

        encrypted_file_bytes = base64.b64decode(encrypted_file_b64)
        if len(encrypted_file_bytes) > 10 * 1024 * 1024:
            return JsonResponse({"error": "Fichier trop volumineux (max 10 MB)."}, status=400)

        medical_file = MedicalFile.objects.create(
            patient=patient,
            encrypted_file=encrypted_file_bytes,
            encrypted_filename=encrypted_filename,
            encrypted_date=encrypted_date,
            file_iv=file_iv,
            uploaded_by=request.user,
            requires_approval=True,
            approved=False,
        )
        for ks_data in key_shares:
            user = User.objects.get(id=ks_data["user_id"])
            FileKeyShare.objects.create(
                file=medical_file,
                user=user,
                encrypted_aes_key=ks_data["encrypted_aes_key"],
            )
        return JsonResponse({"success": True, "file_id": medical_file.id})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_GET
def api_user_public_key(request, user_id):
    """Retourne la cle publique RSA d'un utilisateur (medecin ou patient). Acces connecte."""
    user = get_object_or_404(User, id=user_id)
    try:
        public_key = user.userprofile.public_key
    except Exception:
        public_key = None
    if not public_key:
        return JsonResponse({"error": "Cle publique introuvable."}, status=404)
    return JsonResponse({"user_id": user_id, "public_key": public_key})


@login_required
@role_required("patient")
@require_GET
def api_my_file_keys(request):
    """Retourne tous les FileKeyShare du patient connecte (file_id + encrypted_aes_key).
    Utilise pour le re-chiffrement lors de l'ajout d'un nouveau medecin."""
    key_shares = (
        FileKeyShare.objects
        .filter(file__patient=request.user, user=request.user)
        .select_related("file")
    )
    result = [
        {
            "file_id": ks.file_id,
            "encrypted_aes_key": ks.encrypted_aes_key,
        }
        for ks in key_shares
    ]
    return JsonResponse({"key_shares": result})


@login_required
@role_required("patient")
@require_POST
def api_add_file_key_shares(request):
    """Recoit une liste de {file_id, user_id, encrypted_aes_key} et cree les FileKeyShare.
    Verifie que chaque fichier appartient bien au patient connecte avant creation."""
    try:
        data = json.loads(request.body)
        shares = data.get("shares", [])

        created_count = 0
        for share in shares:
            file_id = share["file_id"]
            user_id = share["user_id"]
            encrypted_aes_key = share["encrypted_aes_key"]

            # Verifier que le fichier appartient au patient connecte
            medical_file = get_object_or_404(MedicalFile, id=file_id, patient=request.user)
            target_user = get_object_or_404(User, id=user_id)

            # Creer ou mettre a jour le FileKeyShare (evite les doublons)
            FileKeyShare.objects.update_or_create(
                file=medical_file,
                user=target_user,
                defaults={"encrypted_aes_key": encrypted_aes_key},
            )
            created_count += 1

        return JsonResponse({"success": True, "created": created_count})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@role_required("patient")
@require_POST
def api_overwrite_file(request, file_id):
    """Ecrase le contenu chiffre d'un fichier existant. La cle AES (FileKeyShare) reste inchangee."""
    medical_file = get_object_or_404(MedicalFile, id=file_id, patient=request.user)
    try:
        data = json.loads(request.body)
        encrypted_file_b64 = data["encrypted_file"]
        encrypted_filename = data["encrypted_filename"]
        encrypted_date = data["encrypted_date"]
        file_iv = data["file_iv"]

        encrypted_file_bytes = base64.b64decode(encrypted_file_b64)
        if len(encrypted_file_bytes) > 10 * 1024 * 1024:
            return JsonResponse({"error": "Fichier trop volumineux (max 10 MB)."}, status=400)

        medical_file.encrypted_file = encrypted_file_bytes
        medical_file.encrypted_filename = encrypted_filename
        medical_file.encrypted_date = encrypted_date
        medical_file.file_iv = file_iv
        medical_file.save(update_fields=["encrypted_file", "encrypted_filename", "encrypted_date", "file_iv"])

        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@role_required("doctor")
@require_POST
def request_file_deletion(request, file_id):
    """Le medecin demande la suppression d'un fichier du patient."""
    medical_file = get_object_or_404(MedicalFile, id=file_id)

    # Verifier que le medecin est associe au patient proprietaire du fichier
    try:
        is_associated = medical_file.patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        return JsonResponse({"error": "Acces refuse."}, status=403)

    deletion_req, created = FileDeletionRequest.objects.get_or_create(
        file=medical_file,
        doctor=request.user,
        defaults={"status": FileDeletionRequest.STATUS_PENDING},
    )
    if not created:
        if deletion_req.status == FileDeletionRequest.STATUS_REJECTED:
            deletion_req.status = FileDeletionRequest.STATUS_PENDING
            deletion_req.save(update_fields=["status", "updated_at"])
            return JsonResponse({"success": True, "message": "Demande renvoyee."})
        return JsonResponse({"success": False, "message": "Une demande est deja en cours."})

    return JsonResponse({"success": True, "message": "Demande envoyee au patient."})


@login_required
@role_required("doctor")
@require_POST
def request_file_modification(request, file_id):
    """Le médecin propose une modification chiffrée d'un fichier patient."""
    medical_file = get_object_or_404(MedicalFile, id=file_id)

    try:
        is_associated = medical_file.patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        return JsonResponse({"error": "Accès refusé."}, status=403)

    try:
        data = json.loads(request.body)
        new_encrypted_file_b64 = data["new_encrypted_file"]
        new_file_iv = data["new_file_iv"]
        new_encrypted_filename = data["new_encrypted_filename"]
        new_encrypted_date = data["new_encrypted_date"]

        new_encrypted_file_bytes = base64.b64decode(new_encrypted_file_b64)
        if len(new_encrypted_file_bytes) > 10 * 1024 * 1024:
            return JsonResponse({"error": "Fichier trop volumineux (max 10 MB)."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

    # Si une demande existe déjà (même fichier, même médecin)
    try:
        mod_req = FileModificationRequest.objects.get(file=medical_file, doctor=request.user)
        # On la remplace si elle a été rejetée ou est déjà en attente
        mod_req.new_encrypted_file = new_encrypted_file_bytes
        mod_req.new_file_iv = new_file_iv
        mod_req.new_encrypted_filename = new_encrypted_filename
        mod_req.new_encrypted_date = new_encrypted_date
        mod_req.status = FileModificationRequest.STATUS_PENDING
        mod_req.save()
        return JsonResponse({"success": True, "message": "Demande mise à jour et renvoyée au patient."})
    except FileModificationRequest.DoesNotExist:
        pass

    FileModificationRequest.objects.create(
        file=medical_file,
        doctor=request.user,
        status=FileModificationRequest.STATUS_PENDING,
        new_encrypted_file=new_encrypted_file_bytes,
        new_file_iv=new_file_iv,
        new_encrypted_filename=new_encrypted_filename,
        new_encrypted_date=new_encrypted_date,
    )
    return JsonResponse({"success": True, "message": "Demande envoyée au patient."})


@login_required
@role_required("patient")
@require_POST
def handle_deletion_request(request, request_id, action):
    """Le patient approuve ou rejette une demande de suppression de fichier."""
    deletion_req = get_object_or_404(
        FileDeletionRequest,
        id=request_id,
        file__patient=request.user,
        status=FileDeletionRequest.STATUS_PENDING,
    )

    if action == "approve":
        medical_file = deletion_req.file
        medical_file.delete()  # supprime aussi les FileKeyShare et les demandes liees (CASCADE)
        return JsonResponse({"success": True, "action": "approved"})
    elif action == "reject":
        deletion_req.status = FileDeletionRequest.STATUS_REJECTED
        deletion_req.save(update_fields=["status", "updated_at"])
        return JsonResponse({"success": True, "action": "rejected"})
    else:
        return JsonResponse({"error": "Action invalide."}, status=400)


@login_required
@role_required("patient")
@require_POST
def handle_modification_request(request, request_id, action):
    """Le patient approuve ou rejette une demande de modification de fichier."""
    mod_req = get_object_or_404(
        FileModificationRequest,
        id=request_id,
        file__patient=request.user,
        status=FileModificationRequest.STATUS_PENDING,
    )

    if action == "approve":
        medical_file = mod_req.file
        medical_file.encrypted_file = bytes(mod_req.new_encrypted_file)
        medical_file.file_iv = mod_req.new_file_iv
        medical_file.encrypted_filename = mod_req.new_encrypted_filename
        medical_file.encrypted_date = mod_req.new_encrypted_date
        medical_file.save(update_fields=["encrypted_file", "file_iv", "encrypted_filename", "encrypted_date"])
        mod_req.status = FileModificationRequest.STATUS_APPROVED
        mod_req.save(update_fields=["status", "updated_at"])
        return JsonResponse({"success": True, "action": "approved"})
    elif action == "reject":
        mod_req.status = FileModificationRequest.STATUS_REJECTED
        mod_req.save(update_fields=["status", "updated_at"])
        return JsonResponse({"success": True, "action": "rejected"})
    else:
        return JsonResponse({"error": "Action invalide."}, status=400)


@login_required
@role_required("doctor")
@require_GET
def api_doctor_patient_keys(request, patient_id):
    """Retourne les cles publiques du patient et de ses medecins (pour upload medecin)."""
    patient = get_object_or_404(User, id=patient_id, userprofile__role="patient")
    try:
        is_associated = patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        return JsonResponse({"error": "Acces refuse."}, status=403)

    # Cle publique du patient
    patient_public_key = None
    try:
        patient_public_key = patient.userprofile.public_key
    except Exception:
        pass

    # Cles publiques de tous les medecins associes au patient
    doctors_list = []
    try:
        for doctor in patient.patient_profile.doctors.select_related("userprofile").all():
            try:
                pub_key = doctor.userprofile.public_key
                if pub_key:
                    doctors_list.append({
                        "user_id": doctor.id,
                        "public_key": pub_key,
                    })
            except Exception:
                pass
    except Exception:
        pass

    return JsonResponse({
        "patient": {
            "user_id": patient.id,
            "public_key": patient_public_key,
        },
        "doctors": doctors_list,
    })
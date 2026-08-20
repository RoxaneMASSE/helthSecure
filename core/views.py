import base64
import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from accounts.decorators import role_required
from .models import DoctorAppointmentRequest, DoctorProfile, FileDeletionRequest, FileKeyShare, MedicalFile, FileModificationRequest

logger = logging.getLogger("security")


def home(request):
    if request.user.is_authenticated:
        try:
            # Clear the profile cache to reload it from the database
            if hasattr(request.user, '_userprofile_cache'):
                del request.user._userprofile_cache
            from accounts.models import UserProfile
            profile = UserProfile.objects.get(user=request.user)

            # Step 1: if the E2E RSA keys have not been generated yet -> setup
            if not profile.public_key:
                return redirect("accounts:setup_keys")

            # Step 2: if the keys are not unlocked for this session -> unlock
            if not request.session.get("keys_unlocked"):
                return redirect("accounts:unlock_keys")

            # Step 3: redirect to the right dashboard depending on the role
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
    # List of the patient's doctors + pending received requests.
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
    # Direct addition of a doctor to the patient's list.
    doctor_id = request.POST.get("doctor_id")
    if not doctor_id:
        messages.error(request, "Invalid doctor.")
        return redirect("core:my_doctors")

    doctor = get_object_or_404(
        User.objects.select_related("userprofile", "doctor_profile"),
        id=doctor_id,
        userprofile__role="doctor",
    )
    patient_profile = request.user.patient_profile
    if patient_profile.doctors.filter(id=doctor.id).exists():
        messages.info(request, "This doctor is already associated.")
        return redirect("core:my_doctors")

    patient_profile.doctors.add(doctor)
    DoctorAppointmentRequest.objects.filter(doctor=doctor, patient=request.user).update(
        status=DoctorAppointmentRequest.STATUS_APPROVED
    )
    messages.success(request, "Doctor added successfully.")
    return redirect("core:my_doctors")


@login_required
@role_required("patient")
@require_POST
def remove_doctor(request, doctor_id):
    # Removes the doctor + deletes the key shares on the patient's files.
    patient_profile = request.user.patient_profile
    doctor = get_object_or_404(User, id=doctor_id, userprofile__role="doctor")

    if not patient_profile.doctors.filter(id=doctor.id).exists():
        messages.error(request, "This doctor is not associated with your profile.")
        return redirect("core:my_doctors")

    patient_profile.doctors.remove(doctor)
    FileKeyShare.objects.filter(file__patient=request.user, user=doctor).delete()
    DoctorAppointmentRequest.objects.filter(doctor=doctor, patient=request.user).update(
        status=DoctorAppointmentRequest.STATUS_REJECTED
    )
    messages.success(request, "Doctor removed and key access revoked.")
    return redirect("core:my_doctors")


@login_required
@role_required("patient")
@require_POST
def handle_request(request, request_id, action):
    # Approve/reject a patient follow-up request.
    appointment_request = get_object_or_404(DoctorAppointmentRequest, id=request_id, patient=request.user)
    if appointment_request.status != DoctorAppointmentRequest.STATUS_PENDING:
        messages.error(request, "This request has already been processed.")
        return redirect("core:my_doctors")

    if action == "approve":
        request.user.patient_profile.doctors.add(appointment_request.doctor)
        appointment_request.status = DoctorAppointmentRequest.STATUS_APPROVED
        appointment_request.save(update_fields=["status", "updated_at"])
        messages.success(request, "Request approved.")
    elif action == "reject":
        appointment_request.status = DoctorAppointmentRequest.STATUS_REJECTED
        appointment_request.save(update_fields=["status", "updated_at"])
        messages.info(request, "Request rejected.")
    else:
        messages.error(request, "Invalid action.")

    return redirect("core:my_doctors")


@login_required
@role_required("patient")
@require_GET
@ratelimit(key="user_or_ip", rate="20/m", method="GET", block=True)
def search_doctors(request):
    # Search doctors by first/last name.
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
    # List of followed patients + sent requests.
    # Note: request.user.patients = M2M to User (patients followed by this doctor)
    # We retrieve the associated PatientProfile via the patient user
    patients = request.user.patients.all()
    sent_requests = DoctorAppointmentRequest.objects.filter(doctor=request.user).select_related("patient")
    context = {
        "patients": patients,
        "sent_requests": sent_requests,
    }
    return render(request, "core/my_patients.html", context)


@login_required
@role_required("doctor")
def medical_records(request):
    # Simplified view: just the list of followed patients with quick access
    # to their files. No follow-request search/management here (see my_patients).
    patients = request.user.patients.all()
    context = {
        "patients": patients,
    }
    return render(request, "core/medical_records.html", context)


@login_required
@role_required("doctor")
@require_POST
def request_patient(request):
    # Send a request to follow a patient.
    patient_id = request.POST.get("patient_id")
    if not patient_id:
        messages.error(request, "Invalid patient.")
        return redirect("core:my_patients")

    patient = get_object_or_404(User.objects.select_related("userprofile"), id=patient_id, userprofile__role="patient")
    if request.user.patients.filter(id=patient.id).exists():
        messages.info(request, "You already follow this patient.")
        return redirect("core:my_patients")

    appointment_request, created = DoctorAppointmentRequest.objects.get_or_create(
        doctor=request.user,
        patient=patient,
        defaults={"status": DoctorAppointmentRequest.STATUS_PENDING},
    )
    if created:
        messages.success(request, "Request sent to the patient.")
    elif appointment_request.status == DoctorAppointmentRequest.STATUS_REJECTED:
        appointment_request.status = DoctorAppointmentRequest.STATUS_PENDING
        appointment_request.save(update_fields=["status", "updated_at"])
        messages.success(request, "Request re-sent to the patient.")
    elif appointment_request.status == DoctorAppointmentRequest.STATUS_PENDING:
        messages.info(request, "A request is already pending for this patient.")
    else:
        messages.info(request, "You already follow this patient.")

    return redirect("core:my_patients")


@login_required
@role_required("doctor")
@require_GET
@ratelimit(key="user_or_ip", rate="20/m", method="GET", block=True)
def search_patients(request):
    # Search patients by username OR email.
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    # Search in username or email, and verify it is indeed a patient
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


# ── E2E medical files ─────────────────────────────────────────────────────────

@login_required
@role_required("patient")
def medical_files(request):
    """Main page: list of the patient's encrypted medical files."""
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

    # Pending deletion requests for this patient's files
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

    # Pending modification requests
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
            # Note: the new encrypted file itself is not sent here,
            # it will be fetched at approval time on the server side.
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
    """Receives the E2E encrypted data and stores the medical file."""
    try:
        data = json.loads(request.body)
        encrypted_file_b64 = data["encrypted_file"]
        encrypted_filename = data["encrypted_filename"]
        encrypted_date = data["encrypted_date"]
        file_iv = data["file_iv"]
        key_shares = data["key_shares"]

        encrypted_file_bytes = base64.b64decode(encrypted_file_b64)
        if len(encrypted_file_bytes) > 10 * 1024 * 1024:
            return JsonResponse({"error": "File too large (max 10 MB)."}, status=400)

        # Only the patient and their currently appointed doctors may receive a key share.
        allowed_user_ids = {request.user.id}
        try:
            allowed_user_ids |= set(request.user.patient_profile.doctors.values_list("id", flat=True))
        except Exception:
            pass
        for ks_data in key_shares:
            if ks_data["user_id"] not in allowed_user_ids:
                logger.warning(
                    "FILE_UPLOAD_INVALID_RECIPIENT user=%s target_user_id=%s",
                    request.user.email, ks_data["user_id"],
                )
                return JsonResponse({"error": "Invalid recipient for key share."}, status=400)

        with transaction.atomic():
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
        logger.info(
            "FILE_UPLOAD user=%s file_id=%s",
            request.user.email, medical_file.id,
        )
        return JsonResponse({"success": True, "file_id": medical_file.id})
    except Exception as e:
        logger.warning("FILE_UPLOAD_FAILED user=%s error=%s", request.user.email, e)
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def download_file(request, file_id):
    """Returns the encrypted file and the encrypted AES key for the logged-in user."""
    medical_file = get_object_or_404(MedicalFile, id=file_id)

    # Block the download if the file requires approval that has not been granted yet
    if medical_file.requires_approval and not medical_file.approved:
        return JsonResponse({"error": "This file has not been approved by the patient yet."}, status=403)

    # Check that the user is the patient OR an associated doctor
    is_patient = (medical_file.patient_id == request.user.id)
    is_doctor = False
    try:
        is_doctor = medical_file.patient.patient_profile.doctors.filter(
            id=request.user.id
        ).exists()
    except Exception:
        pass

    if not (is_patient or is_doctor):
        logger.warning(
            "FILE_ACCESS_DENIED user=%s file_id=%s",
            request.user.email, file_id,
        )
        return JsonResponse({"error": "Access denied."}, status=403)

    ks = get_object_or_404(FileKeyShare, file=medical_file, user=request.user)
    logger.info(
        "FILE_DOWNLOAD user=%s file_id=%s",
        request.user.email, file_id,
    )
    # Encode the binary content in base64 for JSON transport
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
    """Approve or reject a medical file uploaded by a doctor.
    Only the owning patient can approve or reject it."""
    medical_file = get_object_or_404(MedicalFile, id=file_id, patient=request.user)

    # Check that the file actually requires approval
    if not medical_file.requires_approval:
        return JsonResponse({"error": "This file does not require approval."}, status=400)

    action = request.POST.get("action")

    if action == "approve":
        # Mark the file as approved
        medical_file.approved = True
        medical_file.save(update_fields=["approved"])
        logger.info("FILE_APPROVE user=%s file_id=%s", request.user.email, file_id)
        return JsonResponse({"success": True, "action": "approved"})

    elif action == "reject":
        # Delete the file and all its key shares
        medical_file.delete()
        logger.info("FILE_REJECT user=%s file_id=%s", request.user.email, file_id)
        return JsonResponse({"success": True, "action": "rejected"})

    else:
        return JsonResponse({"error": "Invalid action. Use 'approve' or 'reject'."}, status=400)


@login_required
@role_required("patient")
@require_POST
def delete_file(request, file_id):
    """Deletes a medical file and all its key shares."""
    medical_file = get_object_or_404(MedicalFile, id=file_id, patient=request.user)
    medical_file.delete()
    logger.info("FILE_DELETE user=%s file_id=%s", request.user.email, file_id)
    return JsonResponse({"success": True})


@login_required
@role_required("patient")
@require_GET
def api_patient_doctors_keys(request):
    """Returns the patient's public key and those of the associated doctors."""
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
    """Displays a patient's medical files for the associated doctor."""
    patient = get_object_or_404(User, id=patient_id, userprofile__role="patient")
    # Check that the doctor is associated with the patient
    try:
        is_associated = patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        logger.warning(
            "PATIENT_FILES_ACCESS_DENIED user=%s patient_id=%s",
            request.user.email, patient_id,
        )
        messages.error(request, "You are not associated with this patient.")
        return redirect("core:my_patients")

    logger.info(
        "PATIENT_FILES_ACCESS user=%s patient_id=%s",
        request.user.email, patient_id,
    )
    files = (
        MedicalFile.objects
        .filter(patient=patient)
        .prefetch_related("key_shares")
        .order_by("-created_at")
    )
    files_data = []
    for f in files:
        ks = f.key_shares.filter(user=request.user).first()
        # Check whether there is already a pending deletion request by THIS doctor
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
    """Upload of a file by a doctor for a patient. Requires patient validation."""
    patient = get_object_or_404(User, id=patient_id, userprofile__role="patient")
    try:
        is_associated = patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        logger.warning(
            "FILE_UPLOAD_BY_DOCTOR_DENIED user=%s patient_id=%s",
            request.user.email, patient_id,
        )
        return JsonResponse({"error": "Access denied."}, status=403)

    try:
        data = json.loads(request.body)
        encrypted_file_b64 = data["encrypted_file"]
        encrypted_filename = data["encrypted_filename"]
        encrypted_date = data["encrypted_date"]
        file_iv = data["file_iv"]
        key_shares = data["key_shares"]

        encrypted_file_bytes = base64.b64decode(encrypted_file_b64)
        if len(encrypted_file_bytes) > 10 * 1024 * 1024:
            return JsonResponse({"error": "File too large (max 10 MB)."}, status=400)

        # Only the patient and their currently appointed doctors may receive a key share.
        allowed_user_ids = {patient.id}
        try:
            allowed_user_ids |= set(patient.patient_profile.doctors.values_list("id", flat=True))
        except Exception:
            pass
        for ks_data in key_shares:
            if ks_data["user_id"] not in allowed_user_ids:
                logger.warning(
                    "FILE_UPLOAD_BY_DOCTOR_INVALID_RECIPIENT user=%s patient_id=%s target_user_id=%s",
                    request.user.email, patient_id, ks_data["user_id"],
                )
                return JsonResponse({"error": "Invalid recipient for key share."}, status=400)

        with transaction.atomic():
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
        logger.info(
            "FILE_UPLOAD_BY_DOCTOR user=%s patient_id=%s file_id=%s",
            request.user.email, patient_id, medical_file.id,
        )
        return JsonResponse({"success": True, "file_id": medical_file.id})
    except Exception as e:
        logger.warning(
            "FILE_UPLOAD_BY_DOCTOR_FAILED user=%s patient_id=%s error=%s",
            request.user.email, patient_id, e,
        )
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_GET
def api_user_public_key(request, user_id):
    """Returns a user's RSA public key (doctor or patient). Requires login."""
    user = get_object_or_404(User, id=user_id)
    try:
        public_key = user.userprofile.public_key
    except Exception:
        public_key = None
    if not public_key:
        return JsonResponse({"error": "Public key not found."}, status=404)
    return JsonResponse({"user_id": user_id, "public_key": public_key})


@login_required
@role_required("patient")
@require_GET
def api_my_file_keys(request):
    """Returns all FileKeyShare records for the logged-in patient (file_id + encrypted_aes_key).
    Used for re-encryption when adding a new doctor."""
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
    """Receives a list of {file_id, user_id, encrypted_aes_key} and creates the FileKeyShare records.
    Checks that each file actually belongs to the logged-in patient before creation."""
    try:
        data = json.loads(request.body)
        shares = data.get("shares", [])

        # Only the patient and their currently appointed doctors may receive a key share.
        allowed_user_ids = {request.user.id}
        try:
            allowed_user_ids |= set(request.user.patient_profile.doctors.values_list("id", flat=True))
        except Exception:
            pass

        created_count = 0
        for share in shares:
            file_id = share["file_id"]
            user_id = share["user_id"]
            encrypted_aes_key = share["encrypted_aes_key"]

            if user_id not in allowed_user_ids:
                logger.warning(
                    "ADD_KEY_SHARE_INVALID_RECIPIENT user=%s target_user_id=%s",
                    request.user.email, user_id,
                )
                return JsonResponse({"error": "Invalid recipient for key share."}, status=400)

            # Check that the file belongs to the logged-in patient
            medical_file = get_object_or_404(MedicalFile, id=file_id, patient=request.user)
            target_user = get_object_or_404(User, id=user_id)

            # Create or update the FileKeyShare (avoids duplicates)
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
    """Overwrites the encrypted content of an existing file. The AES key (FileKeyShare) is left unchanged."""
    medical_file = get_object_or_404(MedicalFile, id=file_id, patient=request.user)
    try:
        data = json.loads(request.body)
        encrypted_file_b64 = data["encrypted_file"]
        encrypted_filename = data["encrypted_filename"]
        encrypted_date = data["encrypted_date"]
        file_iv = data["file_iv"]

        encrypted_file_bytes = base64.b64decode(encrypted_file_b64)
        if len(encrypted_file_bytes) > 10 * 1024 * 1024:
            return JsonResponse({"error": "File too large (max 10 MB)."}, status=400)

        medical_file.encrypted_file = encrypted_file_bytes
        medical_file.encrypted_filename = encrypted_filename
        medical_file.encrypted_date = encrypted_date
        medical_file.file_iv = file_iv
        medical_file.save(update_fields=["encrypted_file", "encrypted_filename", "encrypted_date", "file_iv"])

        logger.info("FILE_OVERWRITE user=%s file_id=%s", request.user.email, file_id)
        return JsonResponse({"success": True})
    except Exception as e:
        logger.warning("FILE_OVERWRITE_FAILED user=%s file_id=%s error=%s", request.user.email, file_id, e)
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@role_required("doctor")
@require_POST
def request_file_deletion(request, file_id):
    """The doctor requests the deletion of a patient's file."""
    medical_file = get_object_or_404(MedicalFile, id=file_id)

    # Check that the doctor is associated with the owning patient
    try:
        is_associated = medical_file.patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        logger.warning(
            "FILE_DELETION_REQUEST_DENIED user=%s file_id=%s",
            request.user.email, file_id,
        )
        return JsonResponse({"error": "Access denied."}, status=403)

    deletion_req, created = FileDeletionRequest.objects.get_or_create(
        file=medical_file,
        doctor=request.user,
        defaults={"status": FileDeletionRequest.STATUS_PENDING},
    )
    if not created:
        if deletion_req.status == FileDeletionRequest.STATUS_REJECTED:
            deletion_req.status = FileDeletionRequest.STATUS_PENDING
            deletion_req.save(update_fields=["status", "updated_at"])
            logger.info("FILE_DELETION_REQUESTED user=%s file_id=%s", request.user.email, file_id)
            return JsonResponse({"success": True, "message": "Request re-sent."})
        return JsonResponse({"success": False, "message": "A request is already in progress."})

    logger.info("FILE_DELETION_REQUESTED user=%s file_id=%s", request.user.email, file_id)
    return JsonResponse({"success": True, "message": "Request sent to the patient."})


@login_required
@role_required("doctor")
@require_POST
def request_file_modification(request, file_id):
    """The doctor proposes an encrypted modification of a patient's file."""
    medical_file = get_object_or_404(MedicalFile, id=file_id)

    try:
        is_associated = medical_file.patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        logger.warning(
            "FILE_MODIFICATION_REQUEST_DENIED user=%s file_id=%s",
            request.user.email, file_id,
        )
        return JsonResponse({"error": "Access denied."}, status=403)

    try:
        data = json.loads(request.body)
        new_encrypted_file_b64 = data["new_encrypted_file"]
        new_file_iv = data["new_file_iv"]
        new_encrypted_filename = data["new_encrypted_filename"]
        new_encrypted_date = data["new_encrypted_date"]

        new_encrypted_file_bytes = base64.b64decode(new_encrypted_file_b64)
        if len(new_encrypted_file_bytes) > 10 * 1024 * 1024:
            return JsonResponse({"error": "File too large (max 10 MB)."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

    # If a request already exists (same file, same doctor)
    try:
        mod_req = FileModificationRequest.objects.get(file=medical_file, doctor=request.user)
        # Replace it if it was rejected or is already pending
        mod_req.new_encrypted_file = new_encrypted_file_bytes
        mod_req.new_file_iv = new_file_iv
        mod_req.new_encrypted_filename = new_encrypted_filename
        mod_req.new_encrypted_date = new_encrypted_date
        mod_req.status = FileModificationRequest.STATUS_PENDING
        mod_req.save()
        logger.info("FILE_MODIFICATION_REQUESTED user=%s file_id=%s", request.user.email, file_id)
        return JsonResponse({"success": True, "message": "Request updated and re-sent to the patient."})
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
    logger.info("FILE_MODIFICATION_REQUESTED user=%s file_id=%s", request.user.email, file_id)
    return JsonResponse({"success": True, "message": "Request sent to the patient."})


@login_required
@role_required("patient")
@require_POST
def handle_deletion_request(request, request_id, action):
    """The patient approves or rejects a file deletion request."""
    deletion_req = get_object_or_404(
        FileDeletionRequest,
        id=request_id,
        file__patient=request.user,
        status=FileDeletionRequest.STATUS_PENDING,
    )

    if action == "approve":
        medical_file = deletion_req.file
        file_id = medical_file.id
        medical_file.delete()  # also deletes the related FileKeyShare rows and requests (CASCADE)
        logger.info("FILE_DELETION_APPROVED user=%s file_id=%s", request.user.email, file_id)
        return JsonResponse({"success": True, "action": "approved"})
    elif action == "reject":
        deletion_req.status = FileDeletionRequest.STATUS_REJECTED
        deletion_req.save(update_fields=["status", "updated_at"])
        logger.info(
            "FILE_DELETION_REJECTED user=%s file_id=%s",
            request.user.email, deletion_req.file_id,
        )
        return JsonResponse({"success": True, "action": "rejected"})
    else:
        return JsonResponse({"error": "Invalid action."}, status=400)


@login_required
@role_required("patient")
@require_POST
def handle_modification_request(request, request_id, action):
    """The patient approves or rejects a file modification request."""
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
        logger.info(
            "FILE_MODIFICATION_APPROVED user=%s file_id=%s",
            request.user.email, medical_file.id,
        )
        return JsonResponse({"success": True, "action": "approved"})
    elif action == "reject":
        mod_req.status = FileModificationRequest.STATUS_REJECTED
        mod_req.save(update_fields=["status", "updated_at"])
        logger.info(
            "FILE_MODIFICATION_REJECTED user=%s file_id=%s",
            request.user.email, mod_req.file_id,
        )
        return JsonResponse({"success": True, "action": "rejected"})
    else:
        return JsonResponse({"error": "Invalid action."}, status=400)


@login_required
@role_required("doctor")
@require_GET
def api_doctor_patient_keys(request, patient_id):
    """Returns the public keys of the patient and their doctors (for doctor upload)."""
    patient = get_object_or_404(User, id=patient_id, userprofile__role="patient")
    try:
        is_associated = patient.patient_profile.doctors.filter(id=request.user.id).exists()
    except Exception:
        is_associated = False

    if not is_associated:
        return JsonResponse({"error": "Access denied."}, status=403)

    # Patient's public key
    patient_public_key = None
    try:
        patient_public_key = patient.userprofile.public_key
    except Exception:
        pass

    # Public keys of all doctors associated with the patient
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

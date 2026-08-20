import base64
import json
import time

from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import UserProfile
from core.models import FileKeyShare, MedicalFile, PatientProfile
from core.views import home


class HomeRedirectTests(TestCase):
    """
    core.views.home() routes an authenticated user through:
    setup_keys -> unlock_keys -> the right dashboard, based on UserProfile.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="alice@test.com", password="unused")
        self.profile = self.user.userprofile  # auto-created by accounts.models' post_save signal
        self.profile.role = "doctor"
        self.profile.save()

    def _login_with_keys_unlocked(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["keys_unlocked"] = True
        # Also satisfy mozilla_django_oidc.middleware.SessionRefresh, which
        # would otherwise redirect every GET to Keycloak before core.views.home
        # ever runs, since force_login() doesn't set up an OIDC id_token.
        session["oidc_id_token_expiration"] = time.time() + 3600
        session.save()

    def test_redirects_to_dashboard_when_profile_ready(self):
        self.profile.public_key = "fake-public-key"
        self.profile.save()
        self._login_with_keys_unlocked()

        response = self.client.get(reverse("core:home"))

        self.assertRedirects(response, reverse("core:dashboard_doctor"))

    def test_redirects_to_setup_keys_when_public_key_missing(self):
        # keys_unlocked=True bypasses accounts.middleware.KeysUnlockMiddleware,
        # so this exercises home()'s own "Step 1" check directly.
        self._login_with_keys_unlocked()

        response = self.client.get(reverse("core:home"))

        self.assertRedirects(response, reverse("accounts:setup_keys"))


class HomeViewProfileFreshnessTests(TestCase):
    """
    core/views.py:24-25 tries to clear a cached UserProfile off request.user
    before re-fetching it. This proves that line is dead code on the
    installed Django version (4.2), and that home() is correct anyway
    because it re-queries the DB instead of relying on that cache.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="bob", email="bob@test.com", password="unused")
        self.profile = self.user.userprofile
        self.profile.role = "doctor"
        self.profile.public_key = "real-key"
        self.profile.save()

    def _build_request(self):
        request = RequestFactory().get("/")
        request.user = self.user
        SessionMiddleware(lambda r: None).process_request(request)
        request.session["keys_unlocked"] = True
        request.session.save()
        return request

    def test_hasattr_userprofile_cache_is_never_true(self):
        # Django 4.2 caches the reverse O2O accessor in
        # request.user._state.fields_cache["userprofile"], never as a plain
        # "_userprofile_cache" attribute -- so the `if hasattr(...)` guard
        # in home() never passes, regardless of what triggered the request.
        request = self._build_request()
        request.user.userprofile  # populate Django's real cache
        self.assertFalse(hasattr(request.user, "_userprofile_cache"))

    def test_stale_cached_profile_on_request_user_is_ignored(self):
        request = self._build_request()

        # Simulate a stale UserProfile already cached on request.user, as if
        # something earlier in the request (e.g. KeysUnlockMiddleware, which
        # reads request.user.userprofile) had populated it before the DB row
        # was updated.
        stale_profile = UserProfile(user=self.user, role="doctor", public_key=None)
        request.user._state.fields_cache["userprofile"] = stale_profile

        response = home(request)

        # home() still sees the real (non-stale) public_key because it does
        # UserProfile.objects.get(...) directly, not request.user.userprofile.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:dashboard_doctor"))


class FileKeyShareAuthorizationTests(TestCase):
    """
    upload_file / doctor_upload_file / api_add_file_key_shares must only
    accept key_shares whose recipient is the patient themselves or one of
    their currently appointed doctors -- never an arbitrary user_id supplied
    by the client.
    """

    def setUp(self):
        self.patient = User.objects.create_user(username="patient1", email="patient1@test.com", password="unused")
        self.patient.userprofile.role = "patient"
        self.patient.userprofile.save()
        PatientProfile.objects.create(user=self.patient)

        self.doctor = User.objects.create_user(username="doctor1", email="doctor1@test.com", password="unused")
        self.doctor.userprofile.role = "doctor"
        self.doctor.userprofile.save()
        self.patient.patient_profile.doctors.add(self.doctor)

        # A doctor who exists but is NOT appointed to self.patient.
        self.stranger = User.objects.create_user(username="stranger1", email="stranger1@test.com", password="unused")
        self.stranger.userprofile.role = "doctor"
        self.stranger.userprofile.save()

    def _login_with_keys_unlocked(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["keys_unlocked"] = True
        session["oidc_id_token_expiration"] = time.time() + 3600
        session.save()

    def _upload_payload(self, key_shares):
        return json.dumps({
            "encrypted_file": base64.b64encode(b"ciphertext").decode(),
            "encrypted_filename": "enc-name",
            "encrypted_date": "enc-date",
            "file_iv": "enc-iv",
            "key_shares": key_shares,
        })

    # ── upload_file (patient uploading their own file) ─────────────────────

    def test_upload_file_accepts_patient_and_appointed_doctor(self):
        self._login_with_keys_unlocked(self.patient)
        payload = self._upload_payload([
            {"user_id": self.patient.id, "encrypted_aes_key": "wrapped-for-patient"},
            {"user_id": self.doctor.id, "encrypted_aes_key": "wrapped-for-doctor"},
        ])
        response = self.client.post(reverse("core:upload_file"), data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(MedicalFile.objects.count(), 1)
        self.assertEqual(FileKeyShare.objects.count(), 2)

    def test_upload_file_rejects_unrelated_recipient(self):
        self._login_with_keys_unlocked(self.patient)
        payload = self._upload_payload([
            {"user_id": self.patient.id, "encrypted_aes_key": "wrapped-for-patient"},
            {"user_id": self.stranger.id, "encrypted_aes_key": "wrapped-for-stranger"},
        ])
        response = self.client.post(reverse("core:upload_file"), data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid recipient", response.json()["error"])
        # Nothing should have been persisted -- the file creation rolled back too.
        self.assertEqual(MedicalFile.objects.count(), 0)
        self.assertEqual(FileKeyShare.objects.count(), 0)

    # ── doctor_upload_file (appointed doctor uploading on behalf of a patient) ──

    def test_doctor_upload_file_accepts_patient_and_appointed_doctor(self):
        self._login_with_keys_unlocked(self.doctor)
        payload = self._upload_payload([
            {"user_id": self.patient.id, "encrypted_aes_key": "wrapped-for-patient"},
            {"user_id": self.doctor.id, "encrypted_aes_key": "wrapped-for-doctor"},
        ])
        response = self.client.post(
            reverse("core:doctor_upload_file", args=[self.patient.id]),
            data=payload, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(FileKeyShare.objects.count(), 2)

    def test_doctor_upload_file_rejects_unrelated_recipient(self):
        self._login_with_keys_unlocked(self.doctor)
        payload = self._upload_payload([
            {"user_id": self.patient.id, "encrypted_aes_key": "wrapped-for-patient"},
            {"user_id": self.stranger.id, "encrypted_aes_key": "wrapped-for-stranger"},
        ])
        response = self.client.post(
            reverse("core:doctor_upload_file", args=[self.patient.id]),
            data=payload, content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid recipient", response.json()["error"])
        self.assertEqual(MedicalFile.objects.count(), 0)
        self.assertEqual(FileKeyShare.objects.count(), 0)

    # ── api_add_file_key_shares (re-encryption when appointing a new doctor) ──

    def test_add_file_key_shares_accepts_appointed_doctor(self):
        medical_file = MedicalFile.objects.create(
            patient=self.patient, encrypted_file=b"x", encrypted_filename="f",
            encrypted_date="d", file_iv="iv", uploaded_by=self.patient,
        )
        self._login_with_keys_unlocked(self.patient)
        payload = json.dumps({"shares": [
            {"file_id": medical_file.id, "user_id": self.doctor.id, "encrypted_aes_key": "wrapped"},
        ]})
        response = self.client.post(
            reverse("core:api_add_file_key_shares"), data=payload, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FileKeyShare.objects.count(), 1)

    def test_add_file_key_shares_rejects_unrelated_recipient(self):
        medical_file = MedicalFile.objects.create(
            patient=self.patient, encrypted_file=b"x", encrypted_filename="f",
            encrypted_date="d", file_iv="iv", uploaded_by=self.patient,
        )
        self._login_with_keys_unlocked(self.patient)
        payload = json.dumps({"shares": [
            {"file_id": medical_file.id, "user_id": self.stranger.id, "encrypted_aes_key": "wrapped"},
        ]})
        response = self.client.post(
            reverse("core:api_add_file_key_shares"), data=payload, content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(FileKeyShare.objects.count(), 0)

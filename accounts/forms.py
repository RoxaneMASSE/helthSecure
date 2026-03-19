from django import forms
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Checkbox

class PatientRegistrationForm(forms.Form):
    first_name  = forms.CharField(max_length=50, label="First name")
    last_name   = forms.CharField(max_length=50, label="Last name")
    email       = forms.EmailField(label="Email")
    password    = forms.CharField(widget=forms.PasswordInput, label="Password", min_length=8)
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm password")
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Date of birth"
    )
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox, label="")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("confirm_password"):
            raise forms.ValidationError("Passwords do not match.")
        return cleaned


class DoctorRegistrationForm(forms.Form):
    first_name   = forms.CharField(max_length=50, label="First name")
    last_name    = forms.CharField(max_length=50, label="Last name")
    email        = forms.EmailField(label="Email")
    password     = forms.CharField(widget=forms.PasswordInput, label="Password", min_length=8)
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm password")
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Date of birth"
    )
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox, label="")
    
    medical_organisation = forms.CharField(max_length=100, label="Medical organisation")
    certificate = forms.FileField(
        label="Certificate chain (.pem)",
        help_text="Upload your PEM certificate chain (doctor cert + intermediate + root)."
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("confirm_password"):
            raise forms.ValidationError("Passwords do not match.")
        return cleaned
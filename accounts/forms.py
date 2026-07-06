from datetime import date

from django import forms
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Checkbox


def _validate_date_of_birth(date_of_birth):
    """Ensures the date of birth is realistic and the user is an adult."""
    today = date.today()
    if date_of_birth > today:
        raise forms.ValidationError("Date of birth cannot be in the future.")

    age = today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )
    if age < 18:
        raise forms.ValidationError("You must be an adult (18 years or older) to register.")
    if age > 120:
        raise forms.ValidationError("Invalid date of birth.")
    return date_of_birth


class PatientRegistrationForm(forms.Form):
    first_name  = forms.CharField(max_length=50, label="First name")
    last_name   = forms.CharField(max_length=50, label="Last name")
    email       = forms.EmailField(label="Email")
  
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Date of birth"
    )
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox, label="")

    def clean_date_of_birth(self):
        return _validate_date_of_birth(self.cleaned_data["date_of_birth"])



class DoctorRegistrationForm(forms.Form):
    first_name   = forms.CharField(max_length=50, label="First name")
    last_name    = forms.CharField(max_length=50, label="Last name")
    email        = forms.EmailField(label="Email")
   
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

    def clean_date_of_birth(self):
        return _validate_date_of_birth(self.cleaned_data["date_of_birth"])

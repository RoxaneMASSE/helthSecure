from django import forms
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Checkbox

class PatientRegistrationForm(forms.Form):
    first_name  = forms.CharField(max_length=50, label="First name")
    last_name   = forms.CharField(max_length=50, label="Last name")
    email       = forms.EmailField(label="Email")
  
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Date of birth"
    )
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox, label="")



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

   
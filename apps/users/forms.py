from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .identifiers import normalize_phone_number, phone_lookup
from branches.models import Branch
from users.models import PrivacyRequest

User = get_user_model()

_INPUT_CLS = (
    'w-full bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-sm '
    'focus:outline-none focus:ring-2 focus:ring-brand-500'
)


class CustomerLoginForm(forms.Form):
    identifier = forms.CharField(
        label="Phone or Email", max_length=254,
        widget=forms.TextInput(attrs={'class': _INPUT_CLS, 'autofocus': True}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': _INPUT_CLS}),
    )


class CustomerSignupForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False,
        widget=forms.TextInput(attrs={'class': _INPUT_CLS}))
    last_name = forms.CharField(max_length=150, required=False,
        widget=forms.TextInput(attrs={'class': _INPUT_CLS}))
    email = forms.EmailField(required=False,
        widget=forms.EmailInput(attrs={'class': _INPUT_CLS}))
    phone_number = forms.CharField(max_length=15,
        widget=forms.TextInput(attrs={'class': _INPUT_CLS, 'placeholder': '+2547XXXXXXXX'}))
    password = forms.CharField(min_length=8,
        widget=forms.PasswordInput(attrs={'class': _INPUT_CLS}))
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': _INPUT_CLS}))

    def clean_phone_number(self):
        try:
            phone = normalize_phone_number(self.cleaned_data['phone_number'])
        except DjangoValidationError as exc:
            raise forms.ValidationError(list(exc.messages))
        if User.objects.filter(phone_lookup(phone)).exists():
            raise forms.ValidationError("An account with this phone number already exists.")
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_password(self):
        pwd = self.cleaned_data['password']
        try:
            validate_password(pwd)
        except DjangoValidationError as e:
            raise forms.ValidationError(list(e.messages))
        return pwd

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') and cleaned.get('password') != cleaned.get('confirm_password'):
            self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned
    
class OTPVerifyForm(forms.Form):
    code = forms.CharField(
        max_length=6, min_length=6,
        widget=forms.TextInput(attrs={
            'class': _INPUT_CLS, 'autofocus': True,
            'inputmode': 'numeric', 'pattern': '[0-9]{6}',
            'placeholder': '••••••',
        }),
    )


class PasswordResetRequestForm(forms.Form):
    identifier = forms.CharField(
        label="Phone or Email",
        max_length=254,
        widget=forms.TextInput(attrs={
            'class': _INPUT_CLS,
            'autofocus': True,
            'autocomplete': 'username',
        }),
    )

    def clean_identifier(self):
        return self.cleaned_data['identifier'].strip()


class PasswordResetConfirmForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': _INPUT_CLS,
            'autofocus': True,
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
            'autocomplete': 'one-time-code',
        }),
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': _INPUT_CLS,
            'autocomplete': 'new-password',
        }),
    )
    confirm_new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': _INPUT_CLS,
            'autocomplete': 'new-password',
        }),
    )

    def clean_new_password(self):
        password = self.cleaned_data['new_password']
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise forms.ValidationError(list(exc.messages))
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('new_password')
        confirmation = cleaned.get('confirm_new_password')
        if password and confirmation and password != confirmation:
            self.add_error('confirm_new_password', 'Passwords do not match.')
        return cleaned


class CustomerProfileForm(forms.ModelForm):
    """Allow low-risk profile edits; verified identifiers use separate flows."""

    class Meta:
        model = User
        fields = ('first_name', 'last_name')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': _INPUT_CLS, 'autocomplete': 'given-name'}),
            'last_name': forms.TextInput(attrs={'class': _INPUT_CLS, 'autocomplete': 'family-name'}),
        }


class StaffAccountProvisionForm(forms.Form):
    phone_number = forms.CharField(max_length=32, widget=forms.TextInput(attrs={'class': _INPUT_CLS}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': _INPUT_CLS}))
    first_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': _INPUT_CLS}))
    last_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': _INPUT_CLS}))
    role = forms.ChoiceField(widget=forms.Select(attrs={'class': _INPUT_CLS}))
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.none(), widget=forms.Select(attrs={'class': _INPUT_CLS}),
    )

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        if actor.role == User.Role.BRANCH_MANAGER:
            self.fields['role'].choices = [(User.Role.STAFF, 'Branch Staff')]
            self.fields['role'].initial = User.Role.STAFF
            self.fields['role'].widget = forms.HiddenInput()
            self.fields['branch'].initial = actor.branch
            self.fields['branch'].widget = forms.HiddenInput()
        else:
            self.fields['role'].choices = [
                (User.Role.STAFF, 'Branch Staff'),
                (User.Role.INVENTORY_MANAGER, 'Inventory Manager'),
                (User.Role.BRANCH_MANAGER, 'Branch Manager'),
            ]

    def clean_phone_number(self):
        try:
            phone = normalize_phone_number(self.cleaned_data['phone_number'])
        except DjangoValidationError as exc:
            raise forms.ValidationError(list(exc.messages))
        if User.objects.filter(phone_lookup(phone)).exists():
            raise forms.ValidationError('An account with this phone number already exists.')
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email or None


class StaffInviteActivationForm(forms.Form):
    identifier = forms.CharField(max_length=254, widget=forms.TextInput(attrs={'class': _INPUT_CLS}))
    code = forms.RegexField(r'^\d{6}$', widget=forms.TextInput(attrs={
        'class': _INPUT_CLS, 'inputmode': 'numeric', 'autocomplete': 'one-time-code',
    }))
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': _INPUT_CLS, 'autocomplete': 'new-password',
    }))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': _INPUT_CLS, 'autocomplete': 'new-password',
    }))

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('new_password')
        if password and password != cleaned.get('confirm_password'):
            self.add_error('confirm_password', 'Passwords do not match.')
        if password:
            try:
                validate_password(password)
            except DjangoValidationError as exc:
                self.add_error('new_password', forms.ValidationError(list(exc.messages)))
        return cleaned


class PrivacyRequestForm(forms.Form):
    request_type = forms.ChoiceField(
        choices=PrivacyRequest.RequestType.choices,
        widget=forms.Select(attrs={'class': _INPUT_CLS}),
    )
    details = forms.CharField(
        required=False, max_length=2000,
        widget=forms.Textarea(attrs={
            'class': _INPUT_CLS, 'rows': 4,
            'placeholder': 'Describe the records or correction involved.',
        }),
    )
    password = forms.CharField(
        label='Confirm your password',
        widget=forms.PasswordInput(attrs={
            'class': _INPUT_CLS, 'autocomplete': 'current-password',
        }),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise forms.ValidationError('Password confirmation failed.')
        return password


class PrivacyExportForm(forms.Form):
    password = forms.CharField(
        label='Confirm your password',
        widget=forms.PasswordInput(attrs={
            'class': _INPUT_CLS, 'autocomplete': 'current-password',
        }),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise forms.ValidationError('Password confirmation failed.')
        return password

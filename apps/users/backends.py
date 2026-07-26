from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from .identifiers import resolve_user_identifier

User = get_user_model()


class PhoneOrEmailBackend(ModelBackend):
    """
    Authenticates via phone_number, email, or username. Timing-safe:
    when no user matches, still runs a dummy password hash so response
    time is indistinguishable from a real user with a wrong password --
    prevents enumeration of registered phone numbers/emails via timing.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get(User.USERNAME_FIELD)
        if identifier is None or password is None:
            return None
        user = resolve_user_identifier(User, identifier)
        if user is None:
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

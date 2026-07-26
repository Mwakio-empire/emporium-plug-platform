from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh['token_version'] = user.token_version
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class VersionedJWTAuthentication(JWTAuthentication):
    """Reject tokens issued before password reset or global session revocation."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if validated_token.get('token_version') != user.token_version:
            raise AuthenticationFailed('Token has been revoked.', code='token_revoked')
        return user


class VersionedTokenRefreshSerializer(TokenRefreshSerializer):
    """Prevent a revoked refresh token from minting even unusable access tokens."""

    def validate(self, attrs):
        refresh = self.token_class(attrs['refresh'])
        user = User.objects.filter(pk=refresh.get('user_id'), is_active=True).first()
        if user is None or refresh.get('token_version') != user.token_version:
            raise AuthenticationFailed('Token has been revoked.', code='token_revoked')
        return super().validate(attrs)

"""Request and response shapes of the password and email-verification endpoints (P2)."""

from rest_framework import serializers


class PasswordForgotRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetLinkSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)


class PasswordResetRequestSerializer(PasswordResetLinkSerializer):
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)


class PasswordChangeRequestSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128, trim_whitespace=False)
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)


class VerifyEmailRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)


class AccountMessageSerializer(serializers.Serializer):
    detail = serializers.CharField()


class PasswordResetLinkInfoSerializer(serializers.Serializer):
    email = serializers.CharField(help_text="Masked address of the account (`v•••@casaaurora.co`).")


class VerifyEmailResultSerializer(serializers.Serializer):
    email = serializers.EmailField()
    email_verified = serializers.BooleanField()
    already_verified = serializers.BooleanField()


class VerificationResendSerializer(serializers.Serializer):
    sent = serializers.BooleanField()
    email = serializers.EmailField()
    email_verified = serializers.BooleanField()

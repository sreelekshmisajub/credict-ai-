from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from bank_officer.models import BankOfficerProfile
from .models import CustomUser, FinancialProfile
from authentication.validators import validate_real_email, validate_real_name


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
        ]


class RegisterSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(write_only=True)
    organization_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(
        choices=["USER", "BANK_OFFICER"],
        error_messages={
            "invalid_choice": "Public registration supports only User and Bank Officer roles."
        },
    )

    class Meta:
        model = CustomUser
        fields = ["full_name", "email", "organization_name", "password", "role"]
        extra_kwargs = {
            "email": {"required": True},
        }

    def validate_full_name(self, value):
        full_name = validate_real_name(value, "Full name")
        if len(full_name.split()) < 2:
            raise serializers.ValidationError("Please enter your full name.")
        return full_name

    def validate_email(self, value):
        email = validate_real_email(value)
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("This email address is already registered.")
        return email

    def validate_role(self, value):
        if value not in {"USER", "BANK_OFFICER"}:
            raise serializers.ValidationError("Public registration supports only User and Bank Officer roles.")
        return value

    def validate_organization_name(self, value):
        organization_name = (value or "").strip()
        if not organization_name:
            return ""
        return validate_real_name(organization_name, "Bank or financial company")

    def validate_password(self, value):
        email = self.initial_data.get("email", "")
        validate_password(value, CustomUser(username=email or "temp-user", email=email))
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("role") == "BANK_OFFICER" and not (attrs.get("organization_name") or "").strip():
            raise serializers.ValidationError(
                {
                    "organization_name": "Enter the bank, NBFC, or financial company where you work."
                }
            )
        return attrs

    def create(self, validated_data):
        full_name = validated_data.pop("full_name").strip()
        organization_name = validated_data.pop("organization_name", "").strip()
        first_name, *last_name_parts = full_name.split()
        last_name = " ".join(last_name_parts)
        email = validated_data["email"]
        user = CustomUser.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
            first_name=first_name,
            last_name=last_name,
            role=validated_data["role"],
        )
        if user.role == "BANK_OFFICER":
            BankOfficerProfile.objects.create(
                user=user,
                organization_name=organization_name,
            )
        return user


class FinancialProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialProfile
        exclude = ["updated_at"]
        read_only_fields = ["user"]

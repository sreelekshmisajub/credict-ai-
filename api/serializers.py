from rest_framework import serializers

from admin_panel.models import AdminActionLog, SystemAnnouncement
from authentication.models import LoginAudit
from authentication.validators import validate_real_email, validate_real_name
from bank_officer.models import BankOfficerProfile
from credit_prediction.models import FraudAlert, LoanApplication
from users.models import CustomUser, FinancialProfile
from users.serializers import UserSerializer


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False, allow_blank=False)
    username = serializers.CharField(required=False, allow_blank=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        identifier = (attrs.get("identifier") or attrs.get("username") or "").strip()
        if not identifier:
            raise serializers.ValidationError(
                {"identifier": "Enter your email address or username."}
            )
        matched_user = (
            CustomUser.objects.filter(email__iexact=identifier).first()
            or CustomUser.objects.filter(username__iexact=identifier).first()
        )
        attrs["resolved_username"] = matched_user.username if matched_user else identifier
        return attrs


class PredictionRequestSerializer(serializers.Serializer):
    person_age = serializers.IntegerField()
    person_income = serializers.FloatField(required=False)
    monthly_income = serializers.FloatField(required=False)
    person_home_ownership = serializers.ChoiceField(
        choices=["RENT", "OWN", "MORTGAGE", "OTHER"]
    )
    person_emp_length = serializers.FloatField()
    cb_person_cred_hist_length = serializers.IntegerField()
    cb_person_default_on_file = serializers.ChoiceField(choices=["Y", "N"])
    loan_intent = serializers.ChoiceField(
        choices=[
            "PERSONAL",
            "EDUCATION",
            "MEDICAL",
            "VENTURE",
            "HOMEIMPROVEMENT",
            "DEBTCONSOLIDATION",
        ]
    )
    loan_grade = serializers.ChoiceField(choices=list("ABCDEFG"), required=False)
    loan_amnt = serializers.FloatField(required=False)
    loan_int_rate = serializers.FloatField()
    loan_percent_income = serializers.FloatField(required=False)

    def validate(self, attrs):
        annual_income = attrs.get("person_income")
        monthly_income = attrs.get("monthly_income")
        if annual_income in (None, "") and monthly_income in (None, ""):
            raise serializers.ValidationError(
                {
                    "person_income": (
                        "Enter annual income, or provide monthly_income so the API can "
                        "convert it automatically."
                    )
                }
            )
        if annual_income is not None and annual_income <= 0:
            raise serializers.ValidationError(
                {"person_income": "Annual income must be greater than zero."}
            )
        if monthly_income is not None and monthly_income <= 0:
            raise serializers.ValidationError(
                {"monthly_income": "Monthly income must be greater than zero."}
            )
        return attrs

    def split_payload(self):
        data = self.validated_data
        annual_income = data.get("person_income")
        if annual_income in (None, "") and data.get("monthly_income") not in (None, ""):
            annual_income = data["monthly_income"] * 12

        profile_data = {
            key: data[key]
            for key in [
                "person_age",
                "person_home_ownership",
                "person_emp_length",
                "cb_person_cred_hist_length",
                "cb_person_default_on_file",
            ]
        }
        profile_data["person_income"] = annual_income

        application_data = {
            "loan_intent": data["loan_intent"],
            "loan_int_rate": data["loan_int_rate"],
        }
        for key in ["loan_grade", "loan_amnt", "loan_percent_income"]:
            if key in data and data[key] not in (None, ""):
                application_data[key] = data[key]
        return profile_data, application_data


class OfficerDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["APPROVED", "REJECTED", "VERIFICATION_REQUIRED"]
    )
    decision_notes = serializers.CharField(required=False, allow_blank=True)


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["role", "is_active"]


class AdminOfficerSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = BankOfficerProfile
        fields = [
            "id",
            "user",
            "organization_name",
            "employee_id",
            "branch_name",
            "approval_limit",
            "created_at",
            "review_count",
        ]

    def get_review_count(self, obj):
        return obj.user.reviewed_loans.count()


class AdminOfficerCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    organization_name = serializers.CharField()
    employee_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    branch_name = serializers.CharField(required=False, allow_blank=True)
    approval_limit = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        default=0,
    )
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_full_name(self, value):
        full_name = validate_real_name(value, "Full name")
        if len(full_name.split()) < 2:
            raise serializers.ValidationError("Please enter the officer's full name.")
        return full_name

    def validate_email(self, value):
        email = validate_real_email(value)
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("This email address is already registered.")
        return email

    def validate_organization_name(self, value):
        return validate_real_name(value, "Bank or financial company")

    def validate_employee_id(self, value):
        employee_id = (value or "").strip()
        if not employee_id:
            return None
        if BankOfficerProfile.objects.filter(employee_id__iexact=employee_id).exists():
            raise serializers.ValidationError("This employee ID is already in use.")
        return employee_id

    def validate_branch_name(self, value):
        branch_name = (value or "").strip()
        if not branch_name:
            return ""
        return validate_real_name(branch_name, "Branch name")

    def create(self, validated_data):
        full_name = validated_data.pop("full_name").strip()
        first_name, *last_name_parts = full_name.split()
        last_name = " ".join(last_name_parts)
        email = validated_data.pop("email")
        password = validated_data.pop("password")
        is_active = validated_data.pop("is_active", True)
        user = CustomUser.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role="BANK_OFFICER",
            is_active=is_active,
        )
        return BankOfficerProfile.objects.create(user=user, **validated_data)


class AdminOfficerUpdateSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = BankOfficerProfile
        fields = [
            "organization_name",
            "employee_id",
            "branch_name",
            "approval_limit",
            "is_active",
        ]

    def validate_organization_name(self, value):
        return validate_real_name(value, "Bank or financial company")

    def validate_employee_id(self, value):
        employee_id = (value or "").strip()
        if not employee_id:
            return None
        queryset = BankOfficerProfile.objects.exclude(pk=self.instance.pk)
        if queryset.filter(employee_id__iexact=employee_id).exists():
            raise serializers.ValidationError("This employee ID is already in use.")
        return employee_id

    def validate_branch_name(self, value):
        branch_name = (value or "").strip()
        if not branch_name:
            return ""
        return validate_real_name(branch_name, "Branch name")

    def update(self, instance, validated_data):
        is_active = validated_data.pop("is_active", None)
        profile = super().update(instance, validated_data)
        if is_active is not None:
            profile.user.is_active = is_active
            profile.user.save(update_fields=["is_active"])
        return profile


class AdminAnnouncementSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = SystemAnnouncement
        fields = "__all__"


class AdminAnnouncementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemAnnouncement
        fields = ["title", "message", "audience", "is_active"]


class AdminAnnouncementUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemAnnouncement
        fields = ["title", "message", "audience", "is_active"]


class AdminLoginAuditSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = LoginAudit
        fields = ["id", "user", "username_attempt", "successful", "ip_address", "created_at"]


class AdminActionLogSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)

    class Meta:
        model = AdminActionLog
        fields = ["id", "actor", "action_type", "description", "created_at"]


class AdminFinancialDocumentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    document_name = serializers.CharField(source="income_proof_filename", read_only=True)
    document_url = serializers.SerializerMethodField()
    status = serializers.CharField(source="get_income_proof_status_display", read_only=True)

    class Meta:
        model = FinancialProfile
        fields = [
            "id",
            "user",
            "document_name",
            "document_url",
            "status",
            "income_proof_uploaded_at",
        ]

    def get_document_url(self, obj):
        return obj.salary_slip.url if obj.salary_slip else ""

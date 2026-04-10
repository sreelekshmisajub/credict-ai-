from django.core.exceptions import ValidationError

PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com",
    "test.com",
    "mailinator.com",
    "tempmail.com",
}

PLACEHOLDER_TOKENS = {
    "dummy",
    "fake",
    "test",
    "demo",
    "sample",
    "placeholder",
}

PLACEHOLDER_USERNAMES = {
    "admin",
    "testuser",
    "demo",
    "dummy",
    "sample",
    "applicant",
    "borrower",
    "officer",
}


def validate_real_email(email: str):
    normalized = email.strip().lower()
    domain = normalized.split("@")[-1]
    if domain in PLACEHOLDER_EMAIL_DOMAINS:
        raise ValidationError("Please use a real email address, not a placeholder domain.")
    return normalized


def validate_real_name(value: str, field_label: str):
    normalized = value.strip()
    lowered = normalized.lower()
    if not normalized:
        raise ValidationError(f"{field_label} is required.")
    if any(token in lowered for token in PLACEHOLDER_TOKENS):
        raise ValidationError(f"{field_label} cannot contain placeholder text.")
    return normalized


def validate_real_username(username: str):
    normalized = username.strip()
    lowered = normalized.lower()
    if lowered in PLACEHOLDER_USERNAMES:
        raise ValidationError("Please choose a real username, not a placeholder one.")
    if any(token in lowered for token in PLACEHOLDER_TOKENS):
        raise ValidationError("Username cannot contain placeholder text.")
    return normalized

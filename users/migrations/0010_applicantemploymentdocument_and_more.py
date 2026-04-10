from django.db import migrations, models

import users.models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0009_applicantprofile_employment_documents"),
    ]

    operations = [
        migrations.AddField(
            model_name="applicantprofile",
            name="co_applicant_income",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=15, null=True
            ),
        ),
        migrations.AddField(
            model_name="applicantprofile",
            name="co_applicant_name",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="applicantprofile",
            name="co_applicant_relationship",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="applicantprofile",
            name="guarantor_contact",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="applicantprofile",
            name="guarantor_income",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=15, null=True
            ),
        ),
        migrations.AddField(
            model_name="applicantprofile",
            name="guarantor_name",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.CreateModel(
            name="ApplicantEmploymentDocument",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("employment_type", models.CharField(max_length=50)),
                ("document_type", models.CharField(max_length=100)),
                (
                    "file",
                    models.FileField(
                        upload_to=users.models.applicant_employment_document_upload_path
                    ),
                ),
                ("file_name", models.CharField(max_length=255)),
                ("file_path", models.CharField(max_length=500)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "validation_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("VERIFIED", "Verified"),
                            ("REJECTED", "Rejected"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                (
                    "applicant_profile",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="employment_documents",
                        to="users.applicantprofile",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="employment_documents",
                        to="users.customuser",
                    ),
                ),
            ],
            options={
                "ordering": ["uploaded_at"],
                "unique_together": {("applicant_profile", "document_type")},
            },
        ),
        migrations.AlterField(
            model_name="applicantemploymentdocument",
            name="employment_type",
            field=models.CharField(
                choices=[
                    ("SALARIED_GOVT", "Salaried â€” Government / PSU"),
                    ("SALARIED_PRIVATE", "Salaried â€” Private Sector"),
                    (
                        "SELF_EMPLOYED_PROF",
                        "Self-employed Professional (Doctor, CA, Lawyer, Consultant)",
                    ),
                    ("SELF_EMPLOYED_BIZ", "Self-employed Business Owner / Trader"),
                    ("DAILY_WAGE", "Daily Wage / Casual Labourer"),
                    ("FARMER", "Farmer / Agricultural Worker"),
                    ("SEASONAL", "Seasonal Worker"),
                    ("GIG_WORKER", "Gig Worker (Uber, Swiggy, etc.)"),
                    ("PENSIONER", "Pensioner / Retired"),
                    ("HOMEMAKER", "Homemaker"),
                    ("STUDENT_UNEMPLOYED", "Student / Unemployed"),
                    ("NRI", "Non-Resident Indian"),
                ],
                max_length=50,
            ),
        ),
    ]

from django.db import migrations, models

import users.models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0008_customuser_profile_picture"),
    ]

    operations = [
        migrations.AddField(
            model_name="applicantprofile",
            name="employment_document_primary",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=users.models.applicant_primary_document_upload_path,
            ),
        ),
        migrations.AddField(
            model_name="applicantprofile",
            name="employment_document_secondary",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=users.models.applicant_secondary_document_upload_path,
            ),
        ),
    ]

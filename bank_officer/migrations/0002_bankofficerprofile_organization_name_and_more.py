from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bank_officer", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="bankofficerprofile",
            name="organization_name",
            field=models.CharField(default="", max_length=150),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="bankofficerprofile",
            name="branch_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="bankofficerprofile",
            name="employee_id",
            field=models.CharField(blank=True, max_length=32, null=True, unique=True),
        ),
    ]

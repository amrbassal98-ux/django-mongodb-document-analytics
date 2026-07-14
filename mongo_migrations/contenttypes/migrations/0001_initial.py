from django.db import migrations, models
import django_mongodb_backend.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "__first__"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContentType",
            fields=[
                (
                    "id",
                    django_mongodb_backend.fields.ObjectIdAutoField(
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("app_label", models.CharField(max_length=100)),
                ("model", models.CharField(max_length=100)),
            ],
            options={
                "db_table": "django_content_type",
                "managed": True,
            },
        ),
    ]

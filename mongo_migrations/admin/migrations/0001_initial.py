from django.db import migrations, models
import django_mongodb_backend.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0001_initial"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LogEntry",
            fields=[
                (
                    "id",
                    django_mongodb_backend.fields.ObjectIdAutoField(
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("action_time", models.DateTimeField(auto_now=True)),
                (
                    "action_flag",
                    models.PositiveSmallIntegerField(choices=[(1, "Add"), (2, "Change"), (3, "Delete")]),
                ),
                ("action_message", models.TextField(blank=True)),
                (
                    "user",
                    models.ForeignKey(
                        to="auth.user",
                        on_delete=models.CASCADE,
                    ),
                ),
                (
                    "content_type",
                    models.ForeignKey(
                        to="contenttypes.contenttype",
                        on_delete=models.SET_NULL,
                        null=True,
                    ),
                ),
                ("object_id", models.TextField(blank=True, null=True)),
                ("object_repr", models.CharField(max_length=200)),
            ],
            options={
                "db_table": "admin_log_entry",
                "managed": True,
            },
        ),
    ]

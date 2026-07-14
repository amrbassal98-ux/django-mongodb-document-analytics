from django.db import migrations, models
import django_mongodb_backend.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Permission",
            fields=[
                (
                    "id",
                    django_mongodb_backend.fields.ObjectIdAutoField(
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=255, verbose_name="name")),
                (
                    "content_type",
                    models.ForeignKey(
                        to="contenttypes.contenttype",
                        on_delete=models.CASCADE,
                    ),
                ),
                ("codename", models.CharField(max_length=100)),
            ],
            options={
                "db_table": "auth_permission",
                "managed": True,
            },
        ),
        migrations.CreateModel(
            name="Group",
            fields=[
                (
                    "id",
                    django_mongodb_backend.fields.ObjectIdAutoField(
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=150, unique=True)),
                ("permissions", models.ManyToManyField(to="auth.permission")),
            ],
            options={
                "db_table": "auth_group",
                "managed": True,
            },
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    django_mongodb_backend.fields.ObjectIdAutoField(
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("password", models.CharField(max_length=128)),
                ("last_login", models.DateTimeField(blank=True, null=True)),
                ("is_superuser", models.BooleanField(default=False)),
                ("username", models.CharField(max_length=150, unique=True)),
                ("first_name", models.CharField(max_length=150, blank=True)),
                ("last_name", models.CharField(max_length=150, blank=True)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("is_staff", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("date_joined", models.DateTimeField(auto_now_add=True)),
                ("groups", models.ManyToManyField(to="auth.group")),
                ("user_permissions", models.ManyToManyField(to="auth.permission")),
            ],
            options={
                "db_table": "auth_user",
                "managed": True,
            },
        ),
    ]

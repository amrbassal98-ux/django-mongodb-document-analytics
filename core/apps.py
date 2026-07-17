"""App configurations with MongoDB-compatible auto fields."""

from django.contrib.admin.apps import AdminConfig
from django.contrib.auth.apps import AuthConfig
from django.contrib.contenttypes.apps import ContentTypesConfig


class MongoAdminConfig(AdminConfig):
    """Admin app config using MongoDB ObjectId as the default auto field."""
    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'


class MongoAuthConfig(AuthConfig):
    """Auth app config using MongoDB ObjectId as the default auto field."""

    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'


class MongoContentTypeConfig(ContentTypesConfig):
    """ContentTypes app config using MongoDB ObjectId as the default auto field."""
    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'

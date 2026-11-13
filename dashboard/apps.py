from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'
    verbose_name = 'CoreX Hub'

    def ready(self):
        # Sin esto las señales nunca se registraban (no había ready()).
        from . import signals  # noqa: F401

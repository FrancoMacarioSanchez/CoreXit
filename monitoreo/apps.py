from django.apps import AppConfig


class MonitoreoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'monitoreo'
    verbose_name = 'Monitoreo'

    def ready(self):
        from . import signals  # noqa: F401

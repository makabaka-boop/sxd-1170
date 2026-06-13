from django.apps import AppConfig


class HeadphonesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'headphones'
    verbose_name = '耳机管理'

    def ready(self):
        import headphones.signals

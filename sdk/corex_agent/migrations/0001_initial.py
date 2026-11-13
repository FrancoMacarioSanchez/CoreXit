from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='EstadoTenant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('schema_name', models.CharField(max_length=63, unique=True)),
                ('estado', models.CharField(default='activo', max_length=20)),
                ('motivo', models.CharField(blank=True, max_length=255)),
                ('plan', models.JSONField(blank=True, default=dict)),
                ('limites', models.JSONField(blank=True, default=dict)),
                ('referencia_hub', models.CharField(blank=True, max_length=32)),
                ('actualizado', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]

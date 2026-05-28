from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("mapas", "0009_capa_delete_patino"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditoriaEvento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("accion", models.CharField(choices=[("insert", "Inserción"), ("update", "Actualización"), ("delete", "Eliminación")], max_length=20)),
                ("entidad", models.CharField(max_length=120)),
                ("registro_id", models.CharField(blank=True, max_length=64, null=True)),
                ("etiqueta", models.CharField(blank=True, max_length=255, null=True)),
                ("datos_antes", models.JSONField(blank=True, null=True)),
                ("datos_despues", models.JSONField(blank=True, null=True)),
                ("metadatos", models.JSONField(blank=True, default=dict)),
                ("ruta", models.CharField(blank=True, max_length=255, null=True)),
                ("metodo", models.CharField(blank=True, max_length=16, null=True)),
                ("ip_origen", models.GenericIPAddressField(blank=True, null=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="eventos_auditoria", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "auditoria_evento",
                "ordering": ["-creado_en", "-id"],
            },
        ),
    ]

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("mapas", "0005_caparaster"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SolicitudPublicacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("capa", "Capa"), ("grupo_puntos", "Grupo de puntos")], max_length=20)),
                ("capa_id", models.IntegerField(blank=True, null=True)),
                ("capa_nombre", models.CharField(blank=True, max_length=150, null=True)),
                ("grupo_nombre", models.CharField(blank=True, max_length=80, null=True)),
                ("estado", models.CharField(choices=[("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada")], default="pendiente", max_length=20)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="solicitudes_publicacion", to=settings.AUTH_USER_MODEL)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="solicitudes_publicacion_revisadas", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "solicitud_publicacion",
                "ordering": ["-created_at"],
            },
        ),
    ]

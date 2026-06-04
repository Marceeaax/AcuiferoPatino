from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("mapas", "0010_auditoriaevento"),
    ]

    operations = [
        migrations.CreateModel(
            name="SolicitudRegistroUsuario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fec_insercion", models.DateTimeField(blank=True, null=True)),
                ("fec_modificacion", models.DateTimeField(blank=True, null=True)),
                ("email_solicitado", models.EmailField(max_length=254)),
                ("estado", models.CharField(choices=[("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada")], default="pendiente", max_length=20)),
                ("review_comment", models.TextField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="solicitudes_registro_revisadas", to=settings.AUTH_USER_MODEL)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="solicitud_registro", to=settings.AUTH_USER_MODEL)),
                ("usu_insercion", models.ForeignKey(blank=True, db_column="usu_insercion", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("usu_modificacion", models.ForeignKey(blank=True, db_column="usu_modificacion", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "solicitud_registro_usuario",
                "ordering": ["-created_at"],
            },
        ),
    ]

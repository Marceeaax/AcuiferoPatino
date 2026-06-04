from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mapas", "0012_solicitudregistrousuario_datos_personales"),
    ]

    operations = [
        migrations.AddField(
            model_name="preferenciasmapa",
            name="visibilidad_capas",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

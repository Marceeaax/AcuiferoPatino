from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mapas", "0013_preferenciasmapa_visibilidad_capas"),
    ]

    operations = [
        migrations.AddField(
            model_name="preferenciasmapa",
            name="ajustes_visor",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

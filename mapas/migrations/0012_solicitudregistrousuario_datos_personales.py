from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mapas", "0011_solicitudregistrousuario"),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitudregistrousuario",
            name="apellido_solicitado",
            field=models.CharField(default="", max_length=150),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="solicitudregistrousuario",
            name="cedula_solicitada",
            field=models.CharField(default="", max_length=32),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="solicitudregistrousuario",
            name="nombre_solicitado",
            field=models.CharField(default="", max_length=150),
            preserve_default=False,
        ),
    ]

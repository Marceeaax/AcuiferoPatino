from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("mapas", "0007_solicitudpublicacion_review_comment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="caparaster",
            name="fec_insercion",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="caparaster",
            name="fec_modificacion",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="caparaster",
            name="usu_insercion",
            field=models.ForeignKey(
                blank=True,
                db_column="usu_insercion",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="caparaster",
            name="usu_modificacion",
            field=models.ForeignKey(
                blank=True,
                db_column="usu_modificacion",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="preferenciasmapa",
            name="fec_insercion",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="preferenciasmapa",
            name="fec_modificacion",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="preferenciasmapa",
            name="usu_insercion",
            field=models.ForeignKey(
                blank=True,
                db_column="usu_insercion",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="preferenciasmapa",
            name="usu_modificacion",
            field=models.ForeignKey(
                blank=True,
                db_column="usu_modificacion",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="solicitudpublicacion",
            name="fec_insercion",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="solicitudpublicacion",
            name="fec_modificacion",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="solicitudpublicacion",
            name="usu_insercion",
            field=models.ForeignKey(
                blank=True,
                db_column="usu_insercion",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="solicitudpublicacion",
            name="usu_modificacion",
            field=models.ForeignKey(
                blank=True,
                db_column="usu_modificacion",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

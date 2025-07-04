# Generated by Django 5.1.6 on 2025-02-25 18:30

import django.contrib.gis.db.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mapas", "0002_alter_muestreo_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="Patino",
            fields=[
                ("gid", models.AutoField(primary_key=True, serialize=False)),
                (
                    "geom",
                    django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326),
                ),
            ],
            options={
                "db_table": "patino",
                "managed": False,
            },
        ),
    ]

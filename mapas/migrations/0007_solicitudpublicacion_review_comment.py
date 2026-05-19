from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mapas", "0006_solicitudpublicacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitudpublicacion",
            name="review_comment",
            field=models.TextField(blank=True, null=True),
        ),
    ]

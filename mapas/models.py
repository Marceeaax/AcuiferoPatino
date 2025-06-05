from django.contrib.gis.db import models

class Muestreo(models.Model):
    gid = models.AutoField(primary_key=True)
    estacionid = models.CharField(max_length=254, blank=True, null=True)
    codigoorig = models.CharField(max_length=254, blank=True, null=True)
    longitud_x = models.DecimalField(db_column='longitud x', max_digits=65535, decimal_places=65535, blank=True, null=True)  # Field renamed to remove unsuitable characters.
    latitud_y = models.DecimalField(db_column='latitud y', max_digits=65535, decimal_places=65535, blank=True, null=True)  # Field renamed to remove unsuitable characters.
    nombre = models.CharField(max_length=254, blank=True, null=True)
    entidad = models.CharField(max_length=254, blank=True, null=True)
    fecha_toma = models.CharField(db_column='fecha toma', max_length=254, blank=True, null=True)  # Field renamed to remove unsuitable characters.
    alcalinida = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    bicarbonat = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    calcio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    carbonatos = models.FloatField(blank=True, null=True)
    cloruro = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    col_fecale = models.FloatField(db_column='col fecale', blank=True, null=True)  # Field renamed to remove unsuitable characters.
    conductivi = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    dureza_tot = models.FloatField(db_column='dureza tot', blank=True, null=True)  # Field renamed to remove unsuitable characters.
    hierro_tot = models.DecimalField(db_column='hierro tot', max_digits=65535, decimal_places=65535, blank=True, null=True)  # Field renamed to remove unsuitable characters.
    magnesio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    n_amoniaca = models.DecimalField(db_column='n-amoniaca', max_digits=65535, decimal_places=65535, blank=True, null=True)  # Field renamed to remove unsuitable characters.
    nitratos = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    nitritos = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    ph = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    potasio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    sodio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    std = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    sulfatos = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    temperatur = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    turbidez = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    materia_or = models.DecimalField(db_column='materia or', max_digits=65535, decimal_places=65535, blank=True, null=True)  # Field renamed to remove unsuitable characters.
    arsenico = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    mercurio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    manganeso = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    cobre = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    cromo = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    dureza_cal = models.FloatField(db_column='dureza cal', blank=True, null=True)  # Field renamed to remove unsuitable characters.
    dureza_mag = models.FloatField(db_column='dureza mag', blank=True, null=True)  # Field renamed to remove unsuitable characters.
    geom = models.PointField(blank=True, null=True)

    class Meta:
        db_table = "muestreo"  # Usar el nombre exacto de la tabla en PostgreSQL
        managed = False  # Importante: evitar que Django intente modificar la base de datos

    def __str__(self):
        return self.nombre

class Patino(models.Model):
    ogc_fid = models.AutoField(primary_key=True)
    wkb_geometry = models.MultiPolygonField(srid=4326)

    class Meta:
        db_table = "patino"
        managed = False  # No modificar la tabla desde Django

    def __str__(self):
        return f"Patiño {self.gid}"
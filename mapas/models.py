from django.contrib.gis.db import models
from django.contrib.auth.models import User


class AuditFieldsMixin(models.Model):
    fec_insercion = models.DateTimeField(blank=True, null=True)
    usu_insercion = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_column="usu_insercion",
    )
    fec_modificacion = models.DateTimeField(blank=True, null=True)
    usu_modificacion = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_column="usu_modificacion",
    )

    class Meta:
        abstract = True


class Muestreo(AuditFieldsMixin, models.Model):
    gid = models.AutoField(primary_key=True)
    estacionid = models.CharField(max_length=254, blank=True, null=True)
    codigoorig = models.CharField(max_length=254, blank=True, null=True)
    longitud_x = models.DecimalField(db_column='longitud x', max_digits=65535, decimal_places=65535, blank=True, null=True)
    latitud_y = models.DecimalField(db_column='latitud y', max_digits=65535, decimal_places=65535, blank=True, null=True)
    nombre = models.CharField(max_length=254, blank=True, null=True)
    entidad = models.CharField(max_length=254, blank=True, null=True)
    fecha_toma = models.CharField(db_column='fecha toma', max_length=254, blank=True, null=True)
    alcalinida = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    bicarbonat = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    calcio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    carbonatos = models.FloatField(blank=True, null=True)
    cloruro = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    col_fecale = models.FloatField(db_column='col fecale', blank=True, null=True)
    conductivi = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    dureza_tot = models.FloatField(db_column='dureza tot', blank=True, null=True)
    hierro_tot = models.DecimalField(db_column='hierro tot', max_digits=65535, decimal_places=65535, blank=True, null=True)
    magnesio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    n_amoniaca = models.DecimalField(db_column='n-amoniaca', max_digits=65535, decimal_places=65535, blank=True, null=True)
    nitratos = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    nitritos = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    ph = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    potasio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    sodio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    std = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    sulfatos = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    temperatur = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    turbidez = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    materia_or = models.DecimalField(db_column='materia or', max_digits=65535, decimal_places=65535, blank=True, null=True)
    arsenico = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    mercurio = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    manganeso = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    cobre = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    cromo = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    dureza_cal = models.FloatField(db_column='dureza cal', blank=True, null=True)
    dureza_mag = models.FloatField(db_column='dureza mag', blank=True, null=True)
    grupo = models.CharField(max_length=50, blank=True, null=True, default='PATINO1')
    lote_carga = models.CharField(max_length=64, blank=True, null=True)
    archivo_origen = models.CharField(max_length=255, blank=True, null=True)
    srid_origen = models.IntegerField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    publico = models.BooleanField(default=False)
    geom = models.PointField(blank=True, null=True)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="muestreos_personales"
    )

    class Meta:
        db_table = "muestreo"
        managed = False # Con esto, Django no crea automaticamente con el comando makemigrations o migrate 

    def __str__(self):
        return self.nombre or "Muestreo sin nombre"


class Capa(AuditFieldsMixin, models.Model):
    ogc_fid = models.AutoField(primary_key=True)
    wkb_geometry = models.MultiPolygonField(srid=4326)
    nombre = models.CharField(max_length=100, blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "patino"
        managed = False

    def __str__(self):
        return f"Patiño {self.ogc_fid}"
    
    ESTADOS = [
        ('privada', 'Privada'),
        ('pendiente', 'Pendiente de aprobación'),
        ('publica', 'Pública'),
        ('rechazada', 'Rechazada'),
    ]
    estado = models.CharField(max_length=20, choices=ESTADOS, default='privada')


class PreferenciasMapa(AuditFieldsMixin, models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    centro_mapa = models.PointField(null=True, blank=True)

    class Meta:
        db_table = "preferencias_mapa"

    def __str__(self):
        return f"Centro mapa de {self.user.username}"


class CapaRaster(AuditFieldsMixin, models.Model):
    MODOS = [
        ("png", "Imagen PNG"),
        ("geotiff", "GeoTIFF georreferenciado"),
    ]

    nombre = models.CharField(max_length=150)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="capas_raster")
    publico = models.BooleanField(default=False)
    modo_despliegue = models.CharField(max_length=20, choices=MODOS, default="png")
    archivo_original = models.FileField(upload_to="rasters/source/")
    archivo_4326 = models.FileField(upload_to="rasters/processed/")
    archivo_png = models.FileField(upload_to="rasters/png/", blank=True, null=True)
    bounds = models.JSONField(default=list)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "capa_raster"
        ordering = ["-created_at"]

    def __str__(self):
        return self.nombre


class SolicitudPublicacion(AuditFieldsMixin, models.Model):
    TIPO_CAPA = "capa"
    TIPO_GRUPO = "grupo_puntos"
    TIPOS = [
        (TIPO_CAPA, "Capa"),
        (TIPO_GRUPO, "Grupo de puntos"),
    ]

    ESTADO_PENDIENTE = "pendiente"
    ESTADO_APROBADA = "aprobada"
    ESTADO_RECHAZADA = "rechazada"
    ESTADOS = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_APROBADA, "Aprobada"),
        (ESTADO_RECHAZADA, "Rechazada"),
    ]

    requester = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="solicitudes_publicacion",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    capa_id = models.IntegerField(blank=True, null=True)
    capa_nombre = models.CharField(max_length=150, blank=True, null=True)
    grupo_nombre = models.CharField(max_length=80, blank=True, null=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_PENDIENTE)
    review_comment = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="solicitudes_publicacion_revisadas",
        blank=True,
        null=True,
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "solicitud_publicacion"
        ordering = ["-created_at"]

    def __str__(self):
        target = self.capa_nombre or self.grupo_nombre or self.tipo
        return f"{self.get_tipo_display()} - {target} ({self.estado})"

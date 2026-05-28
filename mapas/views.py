# mapas/views.py
"""
Vistas principales del visor del Acuífero Patiño.
Incluye autenticación, gestión de puntos de muestreo, capas, y administración de usuarios.
"""

from django.shortcuts import render, redirect
from django.core.serializers import serialize
from django.conf import settings
from django.db import transaction, connection, ProgrammingError, OperationalError
from django.db.models import Q
from django.http import JsonResponse, Http404, HttpResponse, FileResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.utils import timezone
from django.utils.text import slugify

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, GEOSGeometry, MultiPolygon

import csv
import io
import json
import logging
import re
import shutil
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from .forms import CustomLoginForm
from .models import Muestreo, Capa, PreferenciasMapa, CapaRaster, SolicitudPublicacion, AuditoriaEvento
from .roles import is_map_admin, get_or_create_map_admin_group

import zipfile
import tempfile
import subprocess
import os


ALLOWED_POINT_IMPORT_SRIDS = {4326, 32721}
POINT_IMPORT_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
logger = logging.getLogger(__name__)
POINT_EXPORT_FIELDS = [
    "gid",
    "estacionid",
    "codigoorig",
    "longitud_x",
    "latitud_y",
    "nombre",
    "entidad",
    "fecha_toma",
    "alcalinida",
    "bicarbonat",
    "calcio",
    "carbonatos",
    "cloruro",
    "col_fecale",
    "conductivi",
    "dureza_tot",
    "hierro_tot",
    "magnesio",
    "n_amoniaca",
    "nitratos",
    "nitritos",
    "ph",
    "potasio",
    "sodio",
    "std",
    "sulfatos",
    "temperatur",
    "turbidez",
    "materia_or",
    "arsenico",
    "mercurio",
    "manganeso",
    "cobre",
    "cromo",
    "dureza_cal",
    "dureza_mag",
    "grupo",
    "lote_carga",
    "archivo_origen",
    "srid_origen",
    "activo",
    "publico",
]



# =========================
# Helpers
# =========================
def es_admin(user):
    """Devuelve True si el usuario es staff o pertenece al grupo map_admin."""
    return user.is_authenticated and (
        user.is_staff or user.groups.filter(name='map_admin').exists()
    )


def muestreos_visibles_qs(user):
    if user.is_authenticated:
        return Muestreo.objects.filter(
            Q(user=user) | Q(user__isnull=True) | Q(publico=True),
            activo=True
        ).distinct()
    return Muestreo.objects.filter(
        Q(user__isnull=True) | Q(publico=True),
        activo=True
    ).distinct()


def capas_visibles_qs(user):
    if user.is_authenticated:
        return Capa.objects.filter(Q(user=user) | Q(user__isnull=True))
    return Capa.objects.filter(user__isnull=True)


def rasters_visibles_qs(user):
    if user.is_authenticated:
        return CapaRaster.objects.filter(Q(user=user) | Q(publico=True))
    return CapaRaster.objects.filter(publico=True)


def build_point_export_filename(group=None, formato="csv"):
    base = f"puntos_{slugify(group) if group else 'todos'}"
    ext = "geojson" if formato == "geojson" else "csv"
    return f"{base}.{ext}"


def serialize_points_geojson(qs):
    return serialize(
        "geojson",
        qs,
        geometry_field="geom",
        fields=POINT_EXPORT_FIELDS,
    )


def transformar_punto_a_4326(x, y, srid_origen):
    """
    Convierte coordenadas de origen a EPSG:4326 usando PostGIS.
    Evita depender de geom.transform(...) en Python, que en algunos
    entornos de ejecución estaba devolviendo 'OGR failure'.
    """
    if srid_origen == 4326:
        geom = Point(x, y, srid=4326)
        return geom, x, y

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                ST_AsEWKT(
                    ST_Transform(
                        ST_SetSRID(ST_MakePoint(%s, %s), %s),
                        4326
                    )
                ),
                ST_X(
                    ST_Transform(
                        ST_SetSRID(ST_MakePoint(%s, %s), %s),
                        4326
                    )
                ),
                ST_Y(
                    ST_Transform(
                        ST_SetSRID(ST_MakePoint(%s, %s), %s),
                        4326
                    )
                )
            """,
            [x, y, srid_origen, x, y, srid_origen, x, y, srid_origen],
        )
        row = cursor.fetchone()

    if not row or not row[0]:
        raise ValueError(
            f"No se pudo transformar el punto desde EPSG:{srid_origen} a EPSG:4326."
        )

    geom = GEOSGeometry(row[0], srid=4326)
    return geom, row[1], row[2]


def format_export_value(value):
    if value is None:
        return ""
    return str(value)


def _latest_request_map_for_user(user, tipo):
    """Devuelve el último estado de solicitud por capa o grupo del usuario."""
    try:
        solicitudes = SolicitudPublicacion.objects.filter(
            requester=user,
            tipo=tipo,
        ).order_by("-created_at")
    except ProgrammingError:
        return {}

    latest = {}
    for solicitud in solicitudes:
        key = solicitud.capa_id if tipo == SolicitudPublicacion.TIPO_CAPA else solicitud.grupo_nombre
        if key and key not in latest:
            latest[key] = solicitud
    return latest


def normalizar_columna(valor):
    """Normaliza encabezados de CSV para mapear variantes de nombres."""
    if valor is None:
        return ""
    valor = str(valor).strip().lower()
    reemplazos = str.maketrans(
        "áéíóúüñ()/-",
        "aeiouun    "
    )
    valor = valor.translate(reemplazos)
    valor = valor.replace(".", " ")
    valor = re.sub(r"[^a-z0-9]+", " ", valor)
    return " ".join(valor.split())


def parsear_decimal(valor):
    """Convierte números con coma o punto decimal a float."""
    if valor is None:
        return None

    texto = str(valor).strip()
    if not texto:
        return None

    texto = texto.replace(" ", "")

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


def valor_csv(fila, alias_map, clave):
    """Devuelve el valor CSV usando el primer alias disponible."""
    for alias in alias_map.get(clave, []):
        if alias in fila and str(fila[alias]).strip() != "":
            return fila[alias]
    return None


def leer_texto_subido(archivo, encodings=POINT_IMPORT_ENCODINGS):
    """Intenta leer un archivo de texto con varios encodings comunes."""
    contenido_bytes = archivo.read()
    for encoding in encodings:
        try:
            return contenido_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo decodificar el archivo")


def fila_csv_estructuralmente_vacia(fila):
    if not fila:
        return True
    for valor in fila.values():
        if valor is None:
            continue
        if str(valor).strip():
            return False
    return True


def inferir_srid_probable_desde_coordenadas(x, y):
    """Intenta inferir el SRID más probable a partir de un par X/Y."""
    if x is None or y is None:
        return None
    if -180 <= x <= 180 and -90 <= y <= 90:
        return 4326
    if 100000 <= x <= 900000 and 6000000 <= y <= 9000000:
        return 32721
    return None


def detectar_mismatch_srid_en_filas(filas, alias_map, srid_origen, sample_size=20):
    """
    Busca una pista fuerte de que el SRID elegido no coincide con las coordenadas del archivo.
    Devuelve un dict con el SRID probable y filas de muestra, o None si no hay evidencia suficiente.
    """
    conteos = {}
    muestras = {}

    for idx, fila in enumerate(filas, start=2):
        x = parsear_decimal(valor_csv(fila, alias_map, "x"))
        y = parsear_decimal(valor_csv(fila, alias_map, "y"))
        probable = inferir_srid_probable_desde_coordenadas(x, y)
        if probable is None:
            continue
        conteos[probable] = conteos.get(probable, 0) + 1
        muestras.setdefault(probable, []).append({
            "fila": idx,
            "x": x,
            "y": y,
        })
        if sum(conteos.values()) >= sample_size:
            break

    if not conteos:
        return None

    probable, cantidad = max(conteos.items(), key=lambda item: item[1])
    if probable == srid_origen:
        return None

    return {
        "srid_probable": probable,
        "cantidad": cantidad,
        "muestras": muestras.get(probable, [])[:5],
    }


def timestamp_auditoria():
    return timezone.now()


def audit_create_kwargs(user, when=None):
    when = when or timestamp_auditoria()
    return {
        "fec_insercion": when,
        "usu_insercion": user,
        "fec_modificacion": when,
        "usu_modificacion": user,
    }


def mark_instance_modified(instance, user, when=None):
    when = when or timestamp_auditoria()
    instance.fec_modificacion = when
    instance.usu_modificacion = user
    return when


def audit_update_fields(*field_names):
    fields = {field for field in field_names if field}
    fields.update({"fec_modificacion", "usu_modificacion"})
    return list(fields)


def audit_json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): audit_json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [audit_json_safe(item) for item in value]
    if hasattr(value, "geom_type") and hasattr(value, "extent"):
        minx, miny, maxx, maxy = value.extent
        return {
            "geom_type": value.geom_type,
            "srid": getattr(value, "srid", None),
            "extent": [minx, miny, maxx, maxy],
        }
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "name") and not isinstance(value, str):
        return value.name
    return str(value)


def serialize_instance_for_audit(instance):
    data = {}
    for field in instance._meta.fields:
        if field.attname == "password":
            data[field.attname] = "***"
            continue
        data[field.attname] = audit_json_safe(getattr(instance, field.attname))
    return data


def request_audit_context(request):
    if request is None:
        return {}
    forwarded_for = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    ip_origen = forwarded_for or request.META.get("REMOTE_ADDR")
    return {
        "ruta": request.path[:255] if getattr(request, "path", None) else None,
        "metodo": request.method[:16] if getattr(request, "method", None) else None,
        "ip_origen": ip_origen or None,
    }


def create_audit_event(
    *,
    action,
    actor=None,
    instance=None,
    entity=None,
    record_id=None,
    label=None,
    before=None,
    after=None,
    metadata=None,
    request=None,
):
    if instance is not None:
        entity = entity or instance._meta.label_lower
        pk_field = instance._meta.pk.attname
        record_id = record_id or getattr(instance, pk_field, None)
        label = label or str(instance)

    payload = {
        "actor": actor if getattr(actor, "pk", None) else None,
        "accion": action,
        "entidad": entity or "desconocida",
        "registro_id": str(record_id) if record_id is not None else None,
        "etiqueta": label,
        "datos_antes": audit_json_safe(before),
        "datos_despues": audit_json_safe(after),
        "metadatos": audit_json_safe(metadata or {}),
        **request_audit_context(request),
    }

    try:
        AuditoriaEvento.objects.create(**payload)
    except (ProgrammingError, OperationalError):
        logger.warning("La tabla de auditoría aún no está disponible. Evento omitido: %s", payload["entidad"])


def audit_instance_insert(instance, actor, request=None, metadata=None):
    create_audit_event(
        action="insert",
        actor=actor,
        instance=instance,
        after=serialize_instance_for_audit(instance),
        metadata=metadata,
        request=request,
    )


def audit_instance_update(instance, actor, before, request=None, metadata=None):
    create_audit_event(
        action="update",
        actor=actor,
        instance=instance,
        before=before,
        after=serialize_instance_for_audit(instance),
        metadata=metadata,
        request=request,
    )


def audit_instance_delete(instance, actor, before=None, request=None, metadata=None):
    create_audit_event(
        action="delete",
        actor=actor,
        instance=instance,
        before=before if before is not None else serialize_instance_for_audit(instance),
        metadata=metadata,
        request=request,
    )


def _raster_dirs():
    media_root = Path(settings.MEDIA_ROOT)
    return {
        "tmp": media_root / "rasters" / "tmp",
        "source": media_root / "rasters" / "source",
        "processed": media_root / "rasters" / "processed",
        "png": media_root / "rasters" / "png",
    }


def _ensure_raster_dirs():
    dirs = _raster_dirs()
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _run_command(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def _gdalinfo_json(path):
    result = _run_command(["gdalinfo", "-json", str(path)])
    return json.loads(result.stdout)


def _bounds_from_gdalinfo(info):
    corners = info.get("cornerCoordinates", {})
    upper_left = corners.get("upperLeft")
    lower_right = corners.get("lowerRight")
    if not upper_left or not lower_right:
        raise ValueError("No se pudieron determinar los límites del raster.")
    return [[lower_right[1], upper_left[0]], [upper_left[1], lower_right[0]]]


def _resumen_raster(info):
    band = (info.get("bands") or [{}])[0]
    return {
        "size": info.get("size"),
        "crs": (((info.get("coordinateSystem") or {}).get("wkt", "").split('"')[1:2]) or [None])[0],
        "epsg": next(
            (item.get("code") for item in (info.get("stac") or {}).get("proj:epsg", []) if isinstance(item, dict)),
            None
        ) if isinstance((info.get("stac") or {}).get("proj:epsg"), list) else (info.get("stac") or {}).get("proj:epsg"),
        "band_count": len(info.get("bands") or []),
        "band_type": band.get("type"),
        "nodata": band.get("noDataValue"),
        "pixel_size": info.get("geoTransform")[1:3] if info.get("geoTransform") else None,
        "bounds": _bounds_from_gdalinfo(info),
    }


def _crear_color_relief(path_txt):
    path_txt.write_text(
        "\n".join([
            "0 46 204 113 0",
            "50 46 204 113 200",
            "100 241 196 15 215",
            "200 230 126 34 230",
            "300 192 57 43 240",
            "500 127 0 0 255",
            "nv 0 0 0 0",
        ]),
        encoding="utf-8",
    )


def _procesar_raster(origen_path, base_name):
    dirs = _ensure_raster_dirs()
    processed_tif = dirs["processed"] / f"{base_name}_4326.tif"
    colored_tif = dirs["processed"] / f"{base_name}_colored.tif"
    png_path = dirs["png"] / f"{base_name}.png"
    color_map = dirs["tmp"] / f"{base_name}_colormap.txt"

    _run_command([
        "gdalwarp",
        "-t_srs", "EPSG:4326",
        "-dstalpha",
        "-overwrite",
        str(origen_path),
        str(processed_tif),
    ])

    _crear_color_relief(color_map)
    _run_command([
        "gdaldem",
        "color-relief",
        str(processed_tif),
        str(color_map),
        str(colored_tif),
        "-alpha",
    ])
    _run_command([
        "gdal_translate",
        "-of", "PNG",
        str(colored_tif),
        str(png_path),
    ])

    info_4326 = _gdalinfo_json(processed_tif)
    return {
        "processed_tif": processed_tif,
        "png_path": png_path,
        "colored_tif": colored_tif,
        "color_map": color_map,
        "bounds": _bounds_from_gdalinfo(info_4326),
        "metadata": _resumen_raster(info_4326),
    }


# =========================
# Vistas principales (mapa y auth)
# =========================
def mapa_muestreo_view(request):
    """
    Vista principal del mapa.
    Serializa muestreos y capas (públicas + propias) en formato GeoJSON,
    además de centro preferido y flag de admin.
    """
    if request.user.is_authenticated:
        muestreos_qs = Muestreo.objects.filter(
            Q(user=request.user) | Q(user__isnull=True) | Q(publico=True),
            activo=True
        ).distinct()
        capas_qs = Capa.objects.filter(Q(user=request.user) | Q(user__isnull=True))
        try:
            rasters_qs = list(CapaRaster.objects.filter(Q(user=request.user) | Q(publico=True)))
        except ProgrammingError:
            rasters_qs = []
        try:
            pref = PreferenciasMapa.objects.get(user=request.user)
            centro_mapa = {'lat': pref.centro_mapa.y, 'lng': pref.centro_mapa.x}
        except PreferenciasMapa.DoesNotExist:
            centro_mapa = None
        group_request_states = {}
        try:
            group_request_states = {
                key: {
                    "estado": solicitud.estado,
                    "comentario": solicitud.review_comment or "",
                }
                for key, solicitud in _latest_request_map_for_user(
                    request.user,
                    SolicitudPublicacion.TIPO_GRUPO,
                ).items()
            }
        except ProgrammingError:
            group_request_states = {}
        try:
            pending_admin_requests_count = (
                SolicitudPublicacion.objects.filter(
                    estado=SolicitudPublicacion.ESTADO_PENDIENTE
                ).count()
                if es_admin(request.user) else 0
            )
        except ProgrammingError:
            pending_admin_requests_count = 0
    else:
        muestreos_qs = Muestreo.objects.filter(
            Q(user__isnull=True) | Q(publico=True),
            activo=True
        ).distinct()
        capas_qs = Capa.objects.filter(user__isnull=True)
        try:
            rasters_qs = list(CapaRaster.objects.filter(publico=True))
        except ProgrammingError:
            rasters_qs = []
        centro_mapa = None
        group_request_states = {}
        pending_admin_requests_count = 0

    muestreos = serialize(
        'geojson',
        muestreos_qs,
        geometry_field='geom',
        fields=['id'] + [f.name for f in Muestreo._meta.fields if f.name != 'geom']
    )
    try:
        muestreos_fc = json.loads(muestreos)
        audit_name_map = {
            str(item["gid"]): {
                "usu_insercion_nombre": item.get("usu_insercion__username"),
                "usu_modificacion_nombre": item.get("usu_modificacion__username"),
            }
            for item in muestreos_qs.values(
                "gid",
                "usu_insercion__username",
                "usu_modificacion__username",
            )
        }
        for feature in muestreos_fc.get("features", []):
            feature_id = str(feature.get("id") or feature.get("pk") or "")
            if not feature_id:
                continue
            feature["properties"].update(audit_name_map.get(feature_id, {}))
        muestreos = json.dumps(muestreos_fc)
    except Exception:
        pass

    # 🚩 armar geojson manual con flags de propiedad/publicación
    capas_fc = {"type": "FeatureCollection", "features": []}
    for c in capas_qs:
        geom = json.loads(c.wkb_geometry.geojson)
        capas_fc["features"].append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "id": c.ogc_fid,
                "nombre": c.nombre or "Sin nombre",
                "descripcion": c.descripcion or "",
                "es_publica": c.user_id is None,
                "es_propia": request.user.is_authenticated and c.user_id == request.user.id,
                "estado": getattr(c, "estado", "privada"),
            }
        })

    rasters = [{
        "id": r.id,
        "nombre": r.nombre,
        "publico": r.publico,
        "es_propia": request.user.is_authenticated and r.user_id == request.user.id,
        "modo_despliegue": r.modo_despliegue,
        "archivo_png_url": r.archivo_png.url if r.archivo_png else None,
        "archivo_4326_url": r.archivo_4326.url if r.archivo_4326 else None,
        "bounds": r.bounds,
        "metadata": r.metadata,
    } for r in rasters_qs]

    return render(request, 'mapas/mapa_muestreo.html', {
        'muestreos': muestreos,
        'patino': json.dumps(capas_fc),
        'rasters': json.dumps(rasters),
        'centro_mapa': centro_mapa,
        'es_admin': es_admin(request.user),
        'solicitudes_grupo': json.dumps(group_request_states),
        'solicitudes_admin_pendientes_count': pending_admin_requests_count,
        'login_form': CustomLoginForm(),
    })


def login_view(request):
    """Login con formulario customizado."""
    error = False
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.POST.get("modal_login") == "1"
    )
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if wants_json:
                return JsonResponse({'success': True, 'redirect_url': '/mapa-muestreo/'})
            return redirect('mapa_muestreo')
        else:
            if wants_json:
                return JsonResponse({
                    'success': False,
                    'error': 'Usuario o contraseÃ±a incorrectos.',
                    'field_errors': form.errors,
                }, status=400)
            error = True
    else:
        form = CustomLoginForm()
    return render(request, 'mapas/login.html', {'form': form, 'error': error})


def logout_view(request):
    """Logout y redirección al login."""
    logout(request)
    return redirect('mapa_muestreo')


def register(request):
    """Registro de usuarios, con soporte liviano para modal AJAX en desarrollo."""
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.POST.get("modal_register") == "1"
    )
    if request.method == 'POST':
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""

        if wants_json:
            errors = {}
            if not username:
                errors["username"] = ["Debes ingresar un nombre de usuario."]
            elif User.objects.filter(username=username).exists():
                errors["username"] = ["Ese nombre de usuario ya existe."]

            if not password:
                errors["password"] = ["Debes ingresar una contraseña."]

            if errors:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "No se pudo crear la cuenta.",
                        "field_errors": errors,
                    },
                    status=400,
                )

            user = User.objects.create_user(username=username, password=password)
            audit_instance_insert(
                user,
                user,
                request=request,
                metadata={"origen": "registro-modal"},
            )
            login(request, user)
            return JsonResponse(
                {
                    "success": True,
                    "redirect_url": "/mapa-muestreo/",
                    "message": "Cuenta creada correctamente.",
                }
            )

        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            audit_instance_insert(
                user,
                user,
                request=request,
                metadata={"origen": "registro-form"},
            )
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'mapas/register.html', {'form': form})


@require_GET
def descargar_puntos(request):
    """Descarga puntos visibles como CSV o GeoJSON, opcionalmente filtrados por grupo."""
    formato = (request.GET.get("formato") or "csv").strip().lower()
    grupo = (request.GET.get("grupo") or "").strip()
    if formato not in {"csv", "geojson"}:
        return JsonResponse({"success": False, "error": "Formato no soportado."}, status=400)

    qs = muestreos_visibles_qs(request.user)
    if grupo:
        qs = qs.filter(grupo=grupo)

    if not qs.exists():
        return JsonResponse({"success": False, "error": "No hay puntos disponibles para descargar."}, status=404)

    if formato == "geojson":
        payload = serialize_points_geojson(qs)
        response = HttpResponse(payload, content_type="application/geo+json")
    else:
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        writer = csv.writer(response)
        writer.writerow(POINT_EXPORT_FIELDS)
        for punto in qs:
            writer.writerow([format_export_value(getattr(punto, field, "")) for field in POINT_EXPORT_FIELDS])

    response["Content-Disposition"] = f'attachment; filename="{build_point_export_filename(grupo or None, formato)}"'
    return response


@require_GET
def descargar_capa_geojson(request, ogc_fid):
    """Descarga una capa vectorial visible en formato GeoJSON."""
    try:
        capa = capas_visibles_qs(request.user).get(pk=ogc_fid)
    except Capa.DoesNotExist:
        return JsonResponse({"success": False, "error": "Capa no encontrada o no autorizada."}, status=404)

    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": json.loads(capa.wkb_geometry.geojson),
                "properties": {
                    "id": capa.ogc_fid,
                    "nombre": capa.nombre or "Sin nombre",
                    "descripcion": capa.descripcion or "",
                    "publica": capa.user_id is None,
                },
            }
        ],
    }
    filename = f'capa_{slugify(capa.nombre or f"capa-{capa.ogc_fid}")}.geojson'
    response = HttpResponse(
        json.dumps(feature_collection, ensure_ascii=False),
        content_type="application/geo+json",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_GET
def descargar_raster(request, raster_id):
    """Descarga un raster visible como GeoTIFF o PNG."""
    formato = (request.GET.get("formato") or "geotiff").strip().lower()
    if formato not in {"geotiff", "png"}:
        return JsonResponse({"success": False, "error": "Formato de raster no soportado."}, status=400)

    try:
        raster = rasters_visibles_qs(request.user).get(pk=raster_id)
    except CapaRaster.DoesNotExist:
        return JsonResponse({"success": False, "error": "Raster no encontrado o no autorizado."}, status=404)

    archivo = raster.archivo_4326 if formato == "geotiff" else raster.archivo_png
    if not archivo:
        return JsonResponse({"success": False, "error": "Ese formato no está disponible para este raster."}, status=404)

    filename_base = slugify(raster.nombre or f"raster-{raster.id}") or f"raster-{raster.id}"
    ext = "tif" if formato == "geotiff" else "png"
    content_type = "image/tiff" if formato == "geotiff" else "image/png"
    return FileResponse(
        archivo.open("rb"),
        as_attachment=True,
        filename=f"{filename_base}.{ext}",
        content_type=content_type,
    )


# =========================
# Preferencias del mapa
# =========================
@csrf_exempt
@login_required
def guardar_centro_mapa(request):
    """Guarda el punto central del mapa para el usuario actual."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            lat, lng = data.get('lat'), data.get('lng')
            if lat is None or lng is None:
                return JsonResponse({'success': False, 'error': 'Coordenadas inválidas'}, status=400)

            punto = Point(float(lng), float(lat))
            ahora = timestamp_auditoria()
            preferencias, creada = PreferenciasMapa.objects.get_or_create(
                user=request.user,
                defaults=audit_create_kwargs(request.user, ahora),
            )
            before = None if creada else serialize_instance_for_audit(preferencias)
            preferencias.centro_mapa = punto
            if not creada:
                mark_instance_modified(preferencias, request.user, ahora)
            preferencias.save()
            if creada:
                audit_instance_insert(preferencias, request.user, request=request)
            else:
                audit_instance_update(preferencias, request.user, before, request=request)
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


# =========================
# Muestreos (puntos)
# =========================
@csrf_exempt
@login_required
def guardar_nuevo_punto(request):
    """Guarda un nuevo punto de muestreo asociado al usuario actual."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            grupo = (data.get('grupo') or 'PATINO1').strip()
            lat = float(data.get('lat'))
            lng = float(data.get('lng'))
            ahora = timestamp_auditoria()
            punto = Muestreo(
                estacionid=data.get('estacionid') or None,
                codigoorig=data.get('codigoorig') or None,
                nombre=data.get('nombre'),
                entidad=data.get('entidad') or None,
                fecha_toma=data.get('fecha_toma'),
                n_amoniaca=data.get('n_amoniaca') or None,
                nitritos=data.get('nitritos') or None,
                nitratos=data.get('nitratos') or None,
                alcalinida=data.get('alcalinida') or None,
                materia_or=data.get('materia_or') or None,
                ph=data.get('ph') or None,
                conductivi=data.get('conductivi') or None,
                bicarbonat=data.get('bicarbonat') or None,
                carbonatos=data.get('carbonatos') or None,
                sulfatos=data.get('sulfatos') or None,
                magnesio=data.get('magnesio') or None,
                calcio=data.get('calcio') or None,
                sodio=data.get('sodio') or None,
                potasio=data.get('potasio') or None,
                cloruro=data.get('cloruro') or None,
                arsenico=data.get('arsenico') or None,
                mercurio=data.get('mercurio') or None,
                manganeso=data.get('manganeso') or None,
                cobre=data.get('cobre') or None,
                cromo=data.get('cromo') or None,
                col_fecale=data.get('col_fecale') or None,
                std=data.get('std') or None,
                temperatur=data.get('temperatur') or None,
                turbidez=data.get('turbidez') or None,
                dureza_tot=data.get('dureza_tot') or None,
                hierro_tot=data.get('hierro_tot') or None,
                dureza_cal=data.get('dureza_cal') or None,
                dureza_mag=data.get('dureza_mag') or None,
                grupo=grupo or 'PATINO1',
                lote_carga='MANUAL',
                archivo_origen='manual-web',
                srid_origen=4326,
                activo=True,
                publico=False,
                geom=Point(lng, lat),
                longitud_x=lng,
                latitud_y=lat,
                user=request.user,
                **audit_create_kwargs(request.user, ahora),
            )
            punto.save()
            audit_instance_insert(
                punto,
                request.user,
                request=request,
                metadata={"origen": "manual-web"},
            )
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@require_POST
@login_required
@csrf_protect
def editar_punto_view(request, id):
    """Actualiza un punto propio de muestreo."""
    try:
        data = json.loads(request.body)
        punto = Muestreo.objects.get(gid=id, user=request.user)
        before = serialize_instance_for_audit(punto)
        mark_instance_modified(punto, request.user)

        punto.estacionid = data.get('estacionid') or None
        punto.codigoorig = data.get('codigoorig') or None
        punto.nombre = data.get('nombre')
        punto.entidad = data.get('entidad') or None
        punto.fecha_toma = data.get('fecha_toma')
        punto.grupo = ((data.get('grupo') or 'PATINO1').strip() or 'PATINO1')
        punto.alcalinida = data.get('alcalinida') or None
        punto.bicarbonat = data.get('bicarbonat') or None
        punto.calcio = data.get('calcio') or None
        punto.carbonatos = data.get('carbonatos') or None
        punto.cloruro = data.get('cloruro') or None
        punto.nitratos = data.get('nitratos') or None
        punto.n_amoniaca = data.get('n_amoniaca') or None
        punto.nitritos = data.get('nitritos') or None
        punto.ph = data.get('ph') or None
        punto.potasio = data.get('potasio') or None
        punto.sodio = data.get('sodio') or None
        punto.std = data.get('std') or None
        punto.sulfatos = data.get('sulfatos') or None
        punto.temperatur = data.get('temperatur') or None
        punto.turbidez = data.get('turbidez') or None
        punto.materia_or = data.get('materia_or') or None
        punto.conductivi = data.get('conductivi') or None
        punto.arsenico = data.get('arsenico') or None
        punto.mercurio = data.get('mercurio') or None
        punto.manganeso = data.get('manganeso') or None
        punto.cobre = data.get('cobre') or None
        punto.cromo = data.get('cromo') or None
        punto.col_fecale = data.get('col_fecale') or None
        punto.dureza_tot = data.get('dureza_tot') or None
        punto.hierro_tot = data.get('hierro_tot') or None
        punto.magnesio = data.get('magnesio') or None
        punto.dureza_cal = data.get('dureza_cal') or None
        punto.dureza_mag = data.get('dureza_mag') or None

        lat = data.get('lat')
        lng = data.get('lng')
        if lat is not None and lng is not None and lat != '' and lng != '':
            punto.geom = Point(float(lng), float(lat))
            punto.longitud_x = float(lng)
            punto.latitud_y = float(lat)
            punto.srid_origen = 4326

        punto.save()
        audit_instance_update(punto, request.user, before, request=request)

        return JsonResponse({'success': True})
    except Muestreo.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Punto no encontrado o no autorizado'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST
@login_required
@csrf_protect
def cargar_puntos_csv(request):
    """Carga masiva de puntos de muestreo desde CSV/TSV."""
    archivo = request.FILES.get('archivo')
    srid_origen = request.POST.get('srid', '32721')
    grupo = (request.POST.get('grupo') or 'PATINO1').strip() or 'PATINO1'

    if not archivo:
        return JsonResponse({'success': False, 'error': 'Archivo no recibido.'}, status=400)

    try:
        srid_origen = int(srid_origen)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'SRID de origen invÃ¡lido.'}, status=400)

    if srid_origen not in ALLOWED_POINT_IMPORT_SRIDS:
        soportados = ", ".join(str(valor) for valor in sorted(ALLOWED_POINT_IMPORT_SRIDS))
        return JsonResponse({'success': False, 'error': f'SRID no soportado. UsÃ¡ uno de estos valores: {soportados}.'}, status=400)

    try:
        contenido = leer_texto_subido(archivo)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'No se pudo leer el archivo. ProbÃ¡ guardarlo como CSV UTF-8 o CSV ANSI de Excel.'}, status=400)

    try:
        dialecto = csv.Sniffer().sniff(contenido[:4096], delimiters=';,\t')
    except csv.Error:
        dialecto = csv.excel_tab
        dialecto.delimiter = '\t'

    lector = csv.DictReader(io.StringIO(contenido), dialect=dialecto)
    if not lector.fieldnames:
        return JsonResponse({'success': False, 'error': 'El archivo no tiene encabezados.'}, status=400)

    aliases = {
        'codigo_pozo': ['codigo pozo', 'codigo'],
        'nombre': ['nombre lugar', 'nombre', 'localidad', 'lugar'],
        'x': ['x', 'x utm', 'longitud x', 'lon', 'longitude'],
        'y': ['y', 'y utm', 'latitud y', 'lat', 'latitude'],
        'fecha_toma': ['fecha muestreo', 'fecha toma', 'fecha', 'fecha mues'],
        'n_amoniaca': ['n amoniacal mg l', 'n amoniacal'],
        'nitritos': ['n nitritos mg l', 'n nitritos', 'nitrito mg l', 'nitrito', 'nitritos'],
        'nitratos': ['n nitratos mg l', 'n nitratos', 'nitrato mg l', 'nitrato', 'nitratos'],
        'alcalinida': ['alcalinidad total mg l', 'alcalinidad total', 'alcalinidad'],
        'materia_or': ['materia organica mg l', 'materia organica'],
        'conductivi': ['conductividad us cm', 'conductividad e uscm', 'conductividad'],
        'ph': ['ph'],
        'bicarbonat': ['bicarbonato mg l', 'bicarbonato'],
        'carbonatos': ['carbonato mg l', 'carbonato'],
        'sulfatos': ['sulfato mg l', 'sulfato', 'sulfatos'],
        'magnesio': ['magnesio mg l', 'magnesio'],
        'calcio': ['calcio mg l', 'calcio'],
        'sodio': ['sodio mg l', 'sodio'],
        'potasio': ['potasio mg l', 'potasio'],
        'cloruro': ['cloruro mg l', 'cloruro'],
        'arsenico': ['arsenico mg l', 'arsenico'],
        'mercurio': ['mercurio mg l', 'mercurio'],
        'manganeso': ['manganeso mg l', 'manganeso'],
        'cobre': ['cobre mg l', 'cobre'],
        'cromo': ['cromo total mg l', 'cromo total', 'cromo'],
        'col_fecale': ['coliformes fecales ufc 100 ml', 'col fecal', 'coliformes fecales', 'coliformes']
    }

    filas = []
    for fila in lector:
        fila_normalizada = {normalizar_columna(k): v for k, v in fila.items() if k is not None}
        if fila_csv_estructuralmente_vacia(fila_normalizada):
            continue
        filas.append(fila_normalizada)

    if not filas:
        return JsonResponse({'success': False, 'error': 'El archivo estÃ¡ vacÃ­o.'}, status=400)

    srid_seleccionado = srid_origen
    srid_aplicado = srid_origen
    advertencias = []

    mismatch_srid = detectar_mismatch_srid_en_filas(filas, aliases, srid_origen)
    if mismatch_srid:
        srid_probable = mismatch_srid["srid_probable"]
        detalles = [
            f"Fila {item['fila']}: x={item['x']}, y={item['y']}"
            for item in mismatch_srid["muestras"]
        ]
        if srid_probable in ALLOWED_POINT_IMPORT_SRIDS:
            srid_aplicado = srid_probable
            srid_origen = srid_probable
            advertencias.append({
                'tipo': 'srid_ajustado',
                'mensaje': (
                    f'Se detectó que el archivo parece venir en EPSG:{srid_probable}. '
                    f'Se usó ese SRID como origen y luego los puntos se convirtieron a EPSG:4326 para visualizarlos en el mapa.'
                ),
                'srid_seleccionado': srid_seleccionado,
                'srid_aplicado': srid_probable,
                'detalles': detalles,
            })
            logger.info(
                "Carga CSV de puntos: SRID ajustado automáticamente de %s a %s para %s",
                srid_seleccionado,
                srid_probable,
                archivo.name if getattr(archivo, "name", None) else "archivo_sin_nombre",
            )
        else:
            return JsonResponse({
                'success': False,
                'error': (
                    f'El sistema de coordenadas elegido ({srid_origen}) no coincide con las coordenadas del archivo. '
                    f'Por el rango detectado, parece que deberÃ­as usar EPSG:{srid_probable}.'
                ),
                'detalles': detalles,
                'srid_probable': srid_probable,
                'error_code': 'srid_mismatch',
            }, status=400)

    insertados = 0
    errores = []
    lote_carga = uuid4().hex
    archivo_origen = Path(archivo.name).name if getattr(archivo, 'name', None) else None

    with transaction.atomic():
        for idx, fila in enumerate(filas, start=2):
            try:
                x = parsear_decimal(valor_csv(fila, aliases, 'x'))
                y = parsear_decimal(valor_csv(fila, aliases, 'y'))

                if x is None or y is None:
                    errores.append(f'Fila {idx}: coordenadas x/y invÃ¡lidas.')
                    continue

                geom, longitud_4326, latitud_4326 = transformar_punto_a_4326(
                    x, y, srid_origen
                )
                ahora = timestamp_auditoria()

                punto = Muestreo.objects.create(
                    estacionid=(valor_csv(fila, aliases, 'codigo_pozo') or None),
                    nombre=(valor_csv(fila, aliases, 'nombre') or None),
                    fecha_toma=(valor_csv(fila, aliases, 'fecha_toma') or None),
                    longitud_x=longitud_4326,
                    latitud_y=latitud_4326,
                    grupo=grupo,
                    lote_carga=lote_carga,
                    archivo_origen=archivo_origen,
                    srid_origen=srid_aplicado,
                    activo=True,
                    publico=False,
                    n_amoniaca=parsear_decimal(valor_csv(fila, aliases, 'n_amoniaca')),
                    nitritos=parsear_decimal(valor_csv(fila, aliases, 'nitritos')),
                    nitratos=parsear_decimal(valor_csv(fila, aliases, 'nitratos')),
                    alcalinida=parsear_decimal(valor_csv(fila, aliases, 'alcalinida')),
                    materia_or=parsear_decimal(valor_csv(fila, aliases, 'materia_or')),
                    conductivi=parsear_decimal(valor_csv(fila, aliases, 'conductivi')),
                    ph=parsear_decimal(valor_csv(fila, aliases, 'ph')),
                    bicarbonat=parsear_decimal(valor_csv(fila, aliases, 'bicarbonat')),
                    carbonatos=parsear_decimal(valor_csv(fila, aliases, 'carbonatos')),
                    sulfatos=parsear_decimal(valor_csv(fila, aliases, 'sulfatos')),
                    magnesio=parsear_decimal(valor_csv(fila, aliases, 'magnesio')),
                    calcio=parsear_decimal(valor_csv(fila, aliases, 'calcio')),
                    sodio=parsear_decimal(valor_csv(fila, aliases, 'sodio')),
                    potasio=parsear_decimal(valor_csv(fila, aliases, 'potasio')),
                    cloruro=parsear_decimal(valor_csv(fila, aliases, 'cloruro')),
                    arsenico=parsear_decimal(valor_csv(fila, aliases, 'arsenico')),
                    mercurio=parsear_decimal(valor_csv(fila, aliases, 'mercurio')),
                    manganeso=parsear_decimal(valor_csv(fila, aliases, 'manganeso')),
                    cobre=parsear_decimal(valor_csv(fila, aliases, 'cobre')),
                    cromo=parsear_decimal(valor_csv(fila, aliases, 'cromo')),
                    col_fecale=parsear_decimal(valor_csv(fila, aliases, 'col_fecale')),
                    geom=geom,
                    user=request.user,
                    **audit_create_kwargs(request.user, ahora),
                )
                audit_instance_insert(
                    punto,
                    request.user,
                    request=request,
                    metadata={
                        "origen": "csv",
                        "fila_csv": idx,
                        "grupo": grupo,
                        "lote_carga": lote_carga,
                        "archivo_origen": archivo_origen,
                        "srid_aplicado": srid_aplicado,
                    },
                )
                insertados += 1
            except Exception as e:
                logger.exception(
                    "Error al importar fila %s del CSV %s (srid=%s, x=%s, y=%s)",
                    idx,
                    archivo_origen or "archivo_sin_nombre",
                    srid_origen,
                    fila.get("x"),
                    fila.get("y"),
                )
                errores.append(f'Fila {idx}: {e}')

    if insertados == 0:
        return JsonResponse({'success': False, 'error': 'No se insertÃ³ ningÃºn punto.', 'detalles': errores[:10]}, status=400)

    return JsonResponse({
        'success': True,
        'insertados': insertados,
        'omitidos': len(filas) - insertados,
        'errores': errores[:10],
        'srid_seleccionado': srid_seleccionado,
        'srid_aplicado': srid_aplicado,
        'advertencias': advertencias,
    })


@require_POST
@login_required
@csrf_protect
def cambiar_publicacion_grupo_puntos(request):
    """Solicita publicación o vuelve privado un grupo de puntos propio."""
    try:
        data = json.loads(request.body)
        grupo = (data.get('grupo') or '').strip()
        publico = bool(data.get('publico'))

        if not grupo:
            return JsonResponse({'success': False, 'error': 'Grupo inválido.'}, status=400)

        puntos_qs = Muestreo.objects.filter(user=request.user, grupo=grupo)
        if not puntos_qs.exists():
            return JsonResponse({'success': False, 'error': 'No se encontraron puntos propios para ese grupo.'}, status=404)

        if publico:
            ahora = timestamp_auditoria()
            solicitud, creada = SolicitudPublicacion.objects.get_or_create(
                requester=request.user,
                tipo=SolicitudPublicacion.TIPO_GRUPO,
                grupo_nombre=grupo,
                estado=SolicitudPublicacion.ESTADO_PENDIENTE,
                defaults={
                    "capa_nombre": None,
                    "capa_id": None,
                    **audit_create_kwargs(request.user, ahora),
                },
            )
            if not creada:
                before_solicitud = serialize_instance_for_audit(solicitud)
                mark_instance_modified(solicitud, request.user, ahora)
                solicitud.save(update_fields=audit_update_fields())
                audit_instance_update(
                    solicitud,
                    request.user,
                    before_solicitud,
                    request=request,
                    metadata={"motivo": "reiterar_solicitud_publicacion_grupo"},
                )
            else:
                audit_instance_insert(
                    solicitud,
                    request.user,
                    request=request,
                    metadata={"motivo": "solicitud_publicacion_grupo"},
                )
            return JsonResponse({
                'success': True,
                'grupo': grupo,
                'publico': False,
                'solicitud_creada': creada,
                'estado_solicitud': solicitud.estado,
                'comentario_revision': solicitud.review_comment or '',
                'mensaje': 'La solicitud de publicación fue enviada al administrador.',
            })

        ahora = timestamp_auditoria()
        puntos = list(puntos_qs)
        for punto in puntos:
            before = serialize_instance_for_audit(punto)
            punto.publico = False
            mark_instance_modified(punto, request.user, ahora)
            punto.save(update_fields=audit_update_fields("publico"))
            audit_instance_update(
                punto,
                request.user,
                before,
                request=request,
                metadata={"motivo": "volver_grupo_privado"},
            )
        solicitudes_pendientes = list(SolicitudPublicacion.objects.filter(
            requester=request.user,
            tipo=SolicitudPublicacion.TIPO_GRUPO,
            grupo_nombre=grupo,
            estado=SolicitudPublicacion.ESTADO_PENDIENTE,
        ))
        for solicitud in solicitudes_pendientes:
            before = serialize_instance_for_audit(solicitud)
            solicitud.delete()
            audit_instance_delete(
                solicitud,
                request.user,
                before=before,
                request=request,
                metadata={"motivo": "cancelar_solicitud_grupo_al_volver_privado"},
            )
        return JsonResponse({
            'success': True,
            'grupo': grupo,
            'publico': False,
            'actualizados': len(puntos),
            'estado_solicitud': None,
            'comentario_revision': '',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST
@login_required
@csrf_protect
def renombrar_grupo_puntos(request):
    """Renombra un grupo de puntos propio del usuario actual."""
    try:
        data = json.loads(request.body)
        grupo_actual = (data.get('grupo_actual') or '').strip()
        grupo_nuevo = (data.get('grupo_nuevo') or '').strip()

        if not grupo_actual or not grupo_nuevo:
            return JsonResponse({'success': False, 'error': 'Debes indicar el grupo actual y el nuevo nombre.'}, status=400)

        ahora = timestamp_auditoria()
        puntos = list(Muestreo.objects.filter(
            user=request.user,
            grupo=grupo_actual
        ))
        actualizados = 0
        for punto in puntos:
            before = serialize_instance_for_audit(punto)
            punto.grupo = grupo_nuevo
            mark_instance_modified(punto, request.user, ahora)
            punto.save(update_fields=audit_update_fields("grupo"))
            audit_instance_update(
                punto,
                request.user,
                before,
                request=request,
                metadata={
                    "motivo": "renombrar_grupo",
                    "grupo_actual": grupo_actual,
                    "grupo_nuevo": grupo_nuevo,
                },
            )
            actualizados += 1

        if actualizados == 0:
            return JsonResponse({'success': False, 'error': 'No se encontraron puntos propios para ese grupo.'}, status=404)

        return JsonResponse({
            'success': True,
            'grupo_actual': grupo_actual,
            'grupo_nuevo': grupo_nuevo,
            'actualizados': actualizados
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST
@login_required
@csrf_protect
def eliminar_grupo_puntos(request):
    """Elimina todos los puntos propios del usuario dentro de un grupo."""
    try:
        data = json.loads(request.body)
        grupo = (data.get('grupo') or '').strip()

        if not grupo:
            return JsonResponse({'success': False, 'error': 'Debes indicar un grupo válido.'}, status=400)

        puntos_qs = Muestreo.objects.filter(user=request.user, grupo=grupo)
        puntos = list(puntos_qs)
        eliminados = len(puntos)
        if eliminados == 0:
            return JsonResponse({'success': False, 'error': 'No se encontraron puntos propios para ese grupo.'}, status=404)

        for punto in puntos:
            before = serialize_instance_for_audit(punto)
            punto.delete()
            audit_instance_delete(
                punto,
                request.user,
                before=before,
                request=request,
                metadata={"motivo": "eliminar_grupo", "grupo": grupo},
            )
        solicitudes = list(SolicitudPublicacion.objects.filter(
            requester=request.user,
            tipo=SolicitudPublicacion.TIPO_GRUPO,
            grupo_nombre=grupo,
        ))
        for solicitud in solicitudes:
            before = serialize_instance_for_audit(solicitud)
            solicitud.delete()
            audit_instance_delete(
                solicitud,
                request.user,
                before=before,
                request=request,
                metadata={"motivo": "eliminar_grupo", "grupo": grupo},
            )

        return JsonResponse({
            'success': True,
            'grupo': grupo,
            'eliminados': eliminados,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST
@login_required
@csrf_protect
def eliminar_punto_view(request, id):
    """Elimina un punto de muestreo si pertenece al usuario actual."""
    try:
        punto = Muestreo.objects.get(gid=id, user=request.user)
        before = serialize_instance_for_audit(punto)
        punto.delete()
        audit_instance_delete(punto, request.user, before=before, request=request)
        return JsonResponse({'success': True})
    except Muestreo.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Punto no encontrado o no autorizado'})


# =========================
# Capas
# =========================
@require_POST
@login_required
def cargar_capa_patino(request):
    """Carga una capa desde un archivo GeoJSON y la asocia al usuario actual."""
    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'success': False, 'error': 'Archivo no recibido'}, status=400)

    try:
        data = json.load(archivo)
    except json.JSONDecodeError as e:
        return JsonResponse({'success': False, 'error': f'Error de sintaxis en el GeoJSON: {e}'}, status=400)

    features = []
    gtype = data.get("type")
    if gtype == "FeatureCollection":
        features = data.get("features", [])
    elif gtype == "Feature":
        features = [data]
    elif "type" in data and "coordinates" in data:
        features = [{"type": "Feature", "properties": {}, "geometry": data}]
    else:
        return JsonResponse({'success': False, 'error': 'Estructura GeoJSON no reconocida.'}, status=400)

    insertados, errores = 0, []
    with transaction.atomic():
        for i, feat in enumerate(features, start=1):
            try:
                geom_obj = feat.get("geometry")
                if not geom_obj:
                    errores.append(f'Feature #{i} sin geometry.')
                    continue

                geom = GEOSGeometry(json.dumps(geom_obj), srid=4326)
                if geom.geom_type == 'Polygon':
                    geom = MultiPolygon(geom)
                elif geom.geom_type != 'MultiPolygon':
                    errores.append(f'Feature #{i}: tipo {geom.geom_type} no soportado.')
                    continue

                props = feat.get("properties", {}) or {}
                nombre = props.get("name") or props.get("Nombre") or "Sin nombre"
                ahora = timestamp_auditoria()

                capa = Capa.objects.create(
                    wkb_geometry=geom,
                    user=request.user,
                    nombre=nombre,
                    **audit_create_kwargs(request.user, ahora),
                )
                audit_instance_insert(
                    capa,
                    request.user,
                    request=request,
                    metadata={"origen": "geojson"},
                )
                insertados += 1
            except Exception as e:
                errores.append(f'Feature #{i}: {e}')

    if insertados == 0:
        return JsonResponse({'success': False, 'error': 'No se insertó ninguna geometría.', 'detalles': errores[:5]}, status=400)

    return JsonResponse({'success': True, 'insertados': insertados, 'omitidos': len(features) - insertados, 'errores': errores[:5]})


@require_POST
@login_required
def eliminar_capa_view(request, ogc_fid):
    """Elimina una capa si pertenece al usuario o si es staff."""
    try:
        capa = Capa.objects.get(pk=ogc_fid)
        if capa.user_id == request.user.id or request.user.is_staff:
            before = serialize_instance_for_audit(capa)
            capa.delete()
            audit_instance_delete(capa, request.user, before=before, request=request)
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)
    except Capa.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Capa no encontrada'}, status=404)


@require_GET
@login_required
@user_passes_test(es_admin)
def capas_list_json(request):
    """Lista todas las capas con info básica (solo admins)."""
    sql = """
    SELECT
      c.ogc_fid,
      COALESCE(c.nombre, 'Sin nombre') AS nombre,
      u.id AS user_id,
      u.username AS owner,
      c.fecha_subida,
      ROUND( (ST_Area(c.wkb_geometry::geography) / 1000000.0)::numeric, 3 ) AS area_km2
    FROM patino c
    LEFT JOIN auth_user u ON u.id = c.user_id
    ORDER BY c.ogc_fid DESC;
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    cols = ['ogc_fid', 'nombre', 'user_id', 'owner', 'fecha_subida', 'area_km2']
    data = [dict(zip(cols, r)) for r in rows]
    return JsonResponse({'results': data})


@require_POST
@login_required
@user_passes_test(es_admin)
def hacer_publica_view(request, ogc_fid: int):
    """Convierte una capa en pública (quita el dueño)."""
    try:
        capa = Capa.objects.get(pk=ogc_fid)
    except Capa.DoesNotExist:
        raise Http404("Capa no encontrada")
    before = serialize_instance_for_audit(capa)
    capa.user = None
    mark_instance_modified(capa, request.user)
    capa.save(update_fields=audit_update_fields('user'))
    audit_instance_update(
        capa,
        request.user,
        before,
        request=request,
        metadata={"motivo": "hacer_capa_publica"},
    )
    return JsonResponse({'success': True})


@login_required
def mis_capas_list_json(request):
    """Lista solo las capas propias del usuario logueado."""
    capas = Capa.objects.filter(user=request.user).order_by('-fecha_subida')
    latest_requests = _latest_request_map_for_user(request.user, SolicitudPublicacion.TIPO_CAPA)
    results = [{
        'id': c.ogc_fid,
        'nombre': c.nombre or 'Sin nombre',
        'descripcion': c.descripcion or '',
        'estado': (latest_requests.get(c.ogc_fid).estado if latest_requests.get(c.ogc_fid) else getattr(c, 'estado', 'privada')),
        'comentario_revision': (latest_requests.get(c.ogc_fid).review_comment if latest_requests.get(c.ogc_fid) else ''),
        'fecha_subida': c.fecha_subida.isoformat(),
    } for c in capas]
    return JsonResponse({'results': results})


@require_POST
@login_required
def solicitar_publicacion(request, capa_id):
    """Crea o mantiene una solicitud pendiente de publicación de capa."""
    try:
        capa = Capa.objects.get(pk=capa_id, user=request.user)
        ahora = timestamp_auditoria()
        solicitud, creada = SolicitudPublicacion.objects.get_or_create(
            requester=request.user,
            tipo=SolicitudPublicacion.TIPO_CAPA,
            capa_id=capa_id,
            estado=SolicitudPublicacion.ESTADO_PENDIENTE,
            defaults={
                'capa_nombre': capa.nombre or 'Sin nombre',
                'grupo_nombre': None,
                **audit_create_kwargs(request.user, ahora),
            }
        )
        before_solicitud = None if creada else serialize_instance_for_audit(solicitud)
        if not creada and not solicitud.capa_nombre:
            solicitud.capa_nombre = capa.nombre or 'Sin nombre'
            mark_instance_modified(solicitud, request.user, ahora)
            solicitud.save(update_fields=audit_update_fields('capa_nombre', 'updated_at'))
            audit_instance_update(
                solicitud,
                request.user,
                before_solicitud,
                request=request,
                metadata={"motivo": "actualizar_nombre_solicitud_capa"},
            )
        elif creada:
            audit_instance_insert(
                solicitud,
                request.user,
                request=request,
                metadata={"motivo": "solicitud_publicacion_capa"},
            )

        try:
            before_capa = serialize_instance_for_audit(capa)
            capa.estado = 'pendiente'
            mark_instance_modified(capa, request.user, ahora)
            capa.save(update_fields=audit_update_fields('estado'))
            audit_instance_update(
                capa,
                request.user,
                before_capa,
                request=request,
                metadata={"motivo": "marcar_capa_pendiente_publicacion"},
            )
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'estado': solicitud.estado,
            'solicitud_creada': creada,
        })
    except Capa.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No encontrado'}, status=404)


@require_GET
@login_required
@user_passes_test(es_admin)
def solicitudes_publicacion_list_json(request):
    """Lista solicitudes de publicación pendientes y resueltas para administradores."""
    try:
        pendientes = SolicitudPublicacion.objects.filter(
            estado=SolicitudPublicacion.ESTADO_PENDIENTE
        ).select_related('requester').order_by('-created_at')
        resueltas = SolicitudPublicacion.objects.exclude(
            estado=SolicitudPublicacion.ESTADO_PENDIENTE
        ).select_related('requester', 'reviewed_by').order_by('-reviewed_at', '-updated_at', '-created_at')[:50]
    except ProgrammingError:
        return JsonResponse({'pending': [], 'resolved': []})

    pending_results = [{
        'id': s.id,
        'tipo': s.tipo,
        'objetivo': s.capa_nombre if s.tipo == SolicitudPublicacion.TIPO_CAPA else s.grupo_nombre,
        'requester': s.requester.username,
        'requester_id': s.requester_id,
        'capa_id': s.capa_id,
        'grupo_nombre': s.grupo_nombre,
        'comentario_revision': s.review_comment or '',
        'created_at': s.created_at.isoformat(),
    } for s in pendientes]
    resolved_results = [{
        'id': s.id,
        'tipo': s.tipo,
        'estado': s.estado,
        'objetivo': s.capa_nombre if s.tipo == SolicitudPublicacion.TIPO_CAPA else s.grupo_nombre,
        'requester': s.requester.username,
        'requester_id': s.requester_id,
        'reviewed_by': s.reviewed_by.username if s.reviewed_by else '',
        'comentario_revision': s.review_comment or '',
        'created_at': s.created_at.isoformat(),
        'reviewed_at': s.reviewed_at.isoformat() if s.reviewed_at else None,
    } for s in resueltas]
    return JsonResponse({'pending': pending_results, 'resolved': resolved_results})


@require_POST
@login_required
@user_passes_test(es_admin)
@csrf_protect
def resolver_solicitud_publicacion(request, solicitud_id):
    """Aprueba o rechaza una solicitud pendiente de publicación."""
    try:
        data = json.loads(request.body or '{}')
        decision = (data.get('decision') or '').strip().lower()
        review_comment = (data.get('comentario') or '').strip()
        if decision not in {'aprobar', 'rechazar'}:
            return JsonResponse({'success': False, 'error': 'Decisión inválida.'}, status=400)

        solicitud = SolicitudPublicacion.objects.select_related('requester').get(
            pk=solicitud_id,
            estado=SolicitudPublicacion.ESTADO_PENDIENTE,
        )
        ahora = timestamp_auditoria()
        before_solicitud = serialize_instance_for_audit(solicitud)

        if decision == 'aprobar':
            if solicitud.tipo == SolicitudPublicacion.TIPO_CAPA:
                capa = Capa.objects.get(pk=solicitud.capa_id)
                before_capa = serialize_instance_for_audit(capa)
                capa.user = None
                mark_instance_modified(capa, request.user, ahora)
                capa.save(update_fields=audit_update_fields('user'))
                audit_instance_update(
                    capa,
                    request.user,
                    before_capa,
                    request=request,
                    metadata={"motivo": "aprobar_publicacion_capa"},
                )
                try:
                    before_estado = serialize_instance_for_audit(capa)
                    capa.estado = 'publica'
                    mark_instance_modified(capa, request.user, ahora)
                    capa.save(update_fields=audit_update_fields('estado'))
                    audit_instance_update(
                        capa,
                        request.user,
                        before_estado,
                        request=request,
                        metadata={"motivo": "estado_capa_publica"},
                    )
                except Exception:
                    pass
            elif solicitud.tipo == SolicitudPublicacion.TIPO_GRUPO:
                puntos = list(Muestreo.objects.filter(
                    user=solicitud.requester,
                    grupo=solicitud.grupo_nombre,
                ))
                if not puntos:
                    return JsonResponse({'success': False, 'error': 'No se encontraron puntos para publicar.'}, status=404)
                for punto in puntos:
                    before = serialize_instance_for_audit(punto)
                    punto.publico = True
                    mark_instance_modified(punto, request.user, ahora)
                    punto.save(update_fields=audit_update_fields('publico'))
                    audit_instance_update(
                        punto,
                        request.user,
                        before,
                        request=request,
                        metadata={"motivo": "aprobar_publicacion_grupo", "grupo": solicitud.grupo_nombre},
                    )

            solicitud.estado = SolicitudPublicacion.ESTADO_APROBADA
        else:
            if solicitud.tipo == SolicitudPublicacion.TIPO_CAPA:
                try:
                    capa = Capa.objects.get(pk=solicitud.capa_id, user=solicitud.requester)
                    before_capa = serialize_instance_for_audit(capa)
                    capa.estado = 'rechazada'
                    mark_instance_modified(capa, request.user, ahora)
                    capa.save(update_fields=audit_update_fields('estado'))
                    audit_instance_update(
                        capa,
                        request.user,
                        before_capa,
                        request=request,
                        metadata={"motivo": "rechazar_publicacion_capa"},
                    )
                except Exception:
                    pass
            solicitud.estado = SolicitudPublicacion.ESTADO_RECHAZADA

        solicitud.reviewed_by = request.user
        solicitud.reviewed_at = ahora
        solicitud.review_comment = review_comment or None
        mark_instance_modified(solicitud, request.user, ahora)
        solicitud.save(update_fields=audit_update_fields('estado', 'reviewed_by', 'reviewed_at', 'review_comment', 'updated_at'))
        audit_instance_update(
            solicitud,
            request.user,
            before_solicitud,
            request=request,
            metadata={"motivo": f"resolver_solicitud_{decision}"},
        )

        return JsonResponse({
            'success': True,
            'estado': solicitud.estado,
            'tipo': solicitud.tipo,
            'comentario_revision': solicitud.review_comment or '',
        })
    except SolicitudPublicacion.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Solicitud no encontrada o ya resuelta.'}, status=404)
    except Capa.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'La capa solicitada ya no existe.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =========================
# =========================
# Capas raster TIFF
# =========================
@require_POST
@login_required
@csrf_protect
def preview_capa_tiff(request):
    """Lee metadatos de un GeoTIFF temporal antes de guardarlo."""
    archivo = request.FILES.get("archivo")
    if not archivo or not archivo.name.lower().endswith((".tif", ".tiff")):
        return JsonResponse({"success": False, "error": "Debes subir un archivo TIFF o TIF."}, status=400)

    dirs = _ensure_raster_dirs()
    token = uuid4().hex
    temp_path = dirs["tmp"] / f"{token}.tif"

    with open(temp_path, "wb+") as destino:
        for chunk in archivo.chunks():
            destino.write(chunk)

    try:
        info = _gdalinfo_json(temp_path)
        resumen = _resumen_raster(info)
        return JsonResponse({
            "success": True,
            "token": token,
            "preview": resumen,
        })
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_POST
@login_required
@csrf_protect
def cargar_capa_tiff(request):
    """Guarda un GeoTIFF, lo normaliza a 4326 y genera una vista PNG coloreada."""
    token = (request.POST.get("token") or "").strip()
    nombre = (request.POST.get("nombre") or "").strip()
    modo_despliegue = (request.POST.get("modo_despliegue") or "png").strip()
    publico = request.POST.get("publico") == "true"

    if not token or not nombre:
        return JsonResponse({"success": False, "error": "Nombre o token de preview faltante."}, status=400)
    if modo_despliegue not in {"png", "geotiff"}:
        return JsonResponse({"success": False, "error": "Modo de despliegue inválido."}, status=400)

    dirs = _ensure_raster_dirs()
    temp_path = dirs["tmp"] / f"{token}.tif"
    if not temp_path.exists():
        return JsonResponse({"success": False, "error": "La vista previa expiró. Volvé a seleccionar el archivo."}, status=400)

    base_name = uuid4().hex
    source_path = dirs["source"] / f"{base_name}_{temp_path.name}"
    shutil.move(str(temp_path), str(source_path))

    try:
        procesado = _procesar_raster(source_path, base_name)
        relative_source = source_path.relative_to(settings.MEDIA_ROOT).as_posix()
        relative_tif = procesado["processed_tif"].relative_to(settings.MEDIA_ROOT).as_posix()
        relative_png = procesado["png_path"].relative_to(settings.MEDIA_ROOT).as_posix()
        ahora = timestamp_auditoria()

        raster = CapaRaster.objects.create(
            nombre=nombre,
            user=request.user,
            publico=publico,
            modo_despliegue=modo_despliegue,
            archivo_original=relative_source,
            archivo_4326=relative_tif,
            archivo_png=relative_png,
            bounds=procesado["bounds"],
            metadata=procesado["metadata"],
            **audit_create_kwargs(request.user, ahora),
        )
        audit_instance_insert(
            raster,
            request.user,
            request=request,
            metadata={"origen": "tiff", "modo_despliegue": modo_despliegue},
        )

        for temp_artifact in [procesado["colored_tif"], procesado["color_map"]]:
            temp_artifact = Path(temp_artifact)
            if temp_artifact.exists():
                temp_artifact.unlink()

        return JsonResponse({
            "success": True,
            "id": raster.id,
            "nombre": raster.nombre,
        })
    except Exception as e:
        cleanup = [
            source_path,
            dirs["processed"] / f"{base_name}_4326.tif",
            dirs["processed"] / f"{base_name}_colored.tif",
            dirs["png"] / f"{base_name}.png",
            dirs["tmp"] / f"{base_name}_colormap.txt",
        ]
        for path in cleanup:
            path = Path(path)
            if path.exists():
                path.unlink()
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_POST
@login_required
@csrf_protect
def eliminar_capa_tiff(request, raster_id):
    """Elimina una capa raster propia junto con sus archivos asociados."""
    try:
        raster = CapaRaster.objects.get(pk=raster_id, user=request.user)
    except CapaRaster.DoesNotExist:
        return JsonResponse({"success": False, "error": "Capa raster no encontrada o no autorizada."}, status=404)

    archivos = [
        raster.archivo_original.path if raster.archivo_original else None,
        raster.archivo_4326.path if raster.archivo_4326 else None,
        raster.archivo_png.path if raster.archivo_png else None,
    ]
    before = serialize_instance_for_audit(raster)
    raster.delete()
    audit_instance_delete(raster, request.user, before=before, request=request)
    for archivo in archivos:
        if archivo and os.path.exists(archivo):
            os.remove(archivo)
    return JsonResponse({"success": True})


# Administración de usuarios
# =========================
@require_POST
@login_required
@user_passes_test(is_map_admin)
def make_admin(request, user_id):
    """Promueve un usuario a administrador de mapas."""
    try:
        target = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        raise Http404("Usuario no encontrado")
    before = {
        "user": serialize_instance_for_audit(target),
        "groups": list(target.groups.values_list("name", flat=True)),
    }
    group = get_or_create_map_admin_group()
    target.groups.add(group)
    target.is_staff = True
    target.save()
    after = {
        "user": serialize_instance_for_audit(target),
        "groups": list(target.groups.values_list("name", flat=True)),
    }
    create_audit_event(
        action="update",
        actor=request.user,
        instance=target,
        before=before,
        after=after,
        metadata={"motivo": "otorgar_map_admin"},
        request=request,
    )
    return JsonResponse({"success": True, "message": f"{target.username} ahora es administrador"})


@require_POST
@login_required
@user_passes_test(is_map_admin)
def remove_admin(request, user_id):
    """Revoca privilegios de administrador de un usuario."""
    try:
        target = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        raise Http404("Usuario no encontrado")
    before = {
        "user": serialize_instance_for_audit(target),
        "groups": list(target.groups.values_list("name", flat=True)),
    }
    group = get_or_create_map_admin_group()
    target.groups.remove(group)
    if not target.is_superuser and not target.groups.filter(name=group.name).exists():
        target.is_staff = False
    target.save()
    after = {
        "user": serialize_instance_for_audit(target),
        "groups": list(target.groups.values_list("name", flat=True)),
    }
    create_audit_event(
        action="update",
        actor=request.user,
        instance=target,
        before=before,
        after=after,
        metadata={"motivo": "revocar_map_admin"},
        request=request,
    )
    return JsonResponse({"success": True, "message": f"{target.username} ya no es administrador"})


@require_GET
@login_required
def usuarios_list_json(request):
    """Lista todos los usuarios excepto el actual (solo para admins)."""
    if not es_admin(request.user):
        return JsonResponse({'detail': 'No autorizado'}, status=403)
    users = User.objects.exclude(id=request.user.id).order_by('id').prefetch_related('groups')
    results = [{
        'id': u.id,
        'username': u.username,
        'email': u.email or '',
        'groups': [g.name for g in u.groups.all()],
        'is_staff': u.is_staff,
        'is_superuser': u.is_superuser,
        'last_login': u.last_login.isoformat() if u.last_login else None,
        'date_joined': u.date_joined.isoformat() if u.date_joined else None,
    } for u in users]
    return JsonResponse({'results': results})

@require_POST
@login_required
def cargar_capa_shapefile(request):
    """
    Recibe un ZIP con Shapefile, valida estructura,
    reproyecta a EPSG:4326 e inserta en tabla patino.
    """
    archivo = request.FILES.get('archivo')
    if not archivo or not archivo.name.lower().endswith('.zip'):
        return JsonResponse({'success': False, 'error': 'Debe subir un archivo .zip'}, status=400)

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, archivo.name)

        # Guardar ZIP
        with open(zip_path, 'wb+') as f:
            for chunk in archivo.chunks():
                f.write(chunk)

        # Descomprimir
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(tmpdir)
        except zipfile.BadZipFile:
            return JsonResponse({'success': False, 'error': 'ZIP corrupto'}, status=400)

        # Buscar archivos SHP
        files = os.listdir(tmpdir)
        shp = shx = dbf = prj = None

        for f in files:
            lf = f.lower()
            if lf.endswith('.shp'):
                shp = f
            elif lf.endswith('.shx'):
                shx = f
            elif lf.endswith('.dbf'):
                dbf = f
            elif lf.endswith('.prj'):
                prj = f

        faltantes = [e for e, v in {
            '.shp': shp,
            '.shx': shx,
            '.dbf': dbf,
            '.prj': prj
        }.items() if v is None]

        if faltantes:
            return JsonResponse({
                'success': False,
                'error': 'Shapefile incompleto',
                'faltantes': faltantes
            }, status=400)

        shp_path = os.path.join(tmpdir, shp)

        # Ejecutar ogr2ogr → tabla patino
        try:
            cmd = [
                'ogr2ogr',
                '-f', 'PostgreSQL',
                (
                    f"PG:dbname={connection.settings_dict['NAME']} "
                    f"user={connection.settings_dict['USER']} "
                    f"password={connection.settings_dict['PASSWORD']} "
                    f"host={connection.settings_dict['HOST']} "
                    f"port={connection.settings_dict.get('PORT', 5432)}"
                ),
                shp_path,
                '-nln', 'patino',
                '-append',
                '-lco', 'GEOMETRY_NAME=wkb_geometry',
                '-t_srs', 'EPSG:4326',
                '-nlt', 'MULTIPOLYGON'
            ]

            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            return JsonResponse({
                'success': False,
                'error': 'Error al importar el Shapefile',
                'detalle': str(e)
            }, status=500)

        # Asignar usuario a las geometrías recién cargadas
        ahora = timestamp_auditoria()
        with connection.cursor() as cur:
            cur.execute("""
                UPDATE patino
                SET user_id = %s,
                    fec_insercion = COALESCE(fec_insercion, %s),
                    usu_insercion = COALESCE(usu_insercion, %s),
                    fec_modificacion = %s,
                    usu_modificacion = %s
                RETURNING ogc_fid
                WHERE user_id IS NULL
                AND fecha_subida IS NULL
            """, [request.user.id, ahora, request.user.id, ahora, request.user.id])
            inserted_ids = [row[0] for row in cur.fetchall()]

        if inserted_ids:
            for capa in Capa.objects.filter(ogc_fid__in=inserted_ids):
                audit_instance_insert(
                    capa,
                    request.user,
                    request=request,
                    metadata={"origen": "shapefile", "archivo": archivo.name},
                )

        return JsonResponse({
            'success': True,
            'mensaje': 'Capa Shapefile cargada correctamente'
        })

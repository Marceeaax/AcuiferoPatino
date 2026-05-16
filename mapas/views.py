# mapas/views.py
"""
Vistas principales del visor del Acuífero Patiño.
Incluye autenticación, gestión de puntos de muestreo, capas, y administración de usuarios.
"""

from django.shortcuts import render, redirect
from django.core.serializers import serialize
from django.conf import settings
from django.db import transaction, connection, ProgrammingError
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt, csrf_protect

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, GEOSGeometry, MultiPolygon

import csv
import io
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from .forms import CustomLoginForm
from .models import Muestreo, Capa, PreferenciasMapa, CapaRaster
from .roles import is_map_admin, get_or_create_map_admin_group

import zipfile
import tempfile
import subprocess
import os



# =========================
# Helpers
# =========================
def es_admin(user):
    """Devuelve True si el usuario es staff o pertenece al grupo map_admin."""
    return user.is_authenticated and (
        user.is_staff or user.groups.filter(name='map_admin').exists()
    )


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

    muestreos = serialize(
        'geojson',
        muestreos_qs,
        geometry_field='geom',
        fields=['id'] + [f.name for f in Muestreo._meta.fields if f.name != 'geom']
    )

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
    })


def login_view(request):
    """Login con formulario customizado."""
    error = False
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('mapa_muestreo')
        else:
            error = True
    else:
        form = CustomLoginForm()
    return render(request, 'mapas/login.html', {'form': form, 'error': error})


def logout_view(request):
    """Logout y redirección al login."""
    logout(request)
    return redirect('login')


def register(request):
    """Registro básico de usuarios con UserCreationForm."""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'mapas/register.html', {'form': form})


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
            preferencias, _ = PreferenciasMapa.objects.get_or_create(user=request.user)
            preferencias.centro_mapa = punto
            preferencias.save()
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
            punto = Muestreo(
                nombre=data.get('nombre'),
                fecha_toma=data.get('fecha_toma'),
                nitratos=data.get('nitratos') or None,
                ph=data.get('ph') or None,
                conductivi=data.get('conductivi') or None,
                arsenico=data.get('arsenico') or None,
                col_fecale=data.get('col_fecale') or None,
                grupo=grupo or 'PATINO1',
                activo=True,
                publico=False,
                geom=Point(float(data.get('lng')), float(data.get('lat'))),
                user=request.user
            )
            punto.save()
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

        punto.save()

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

    try:
        contenido = archivo.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        return JsonResponse({'success': False, 'error': 'No se pudo leer el archivo. Guardalo como CSV UTF-8.'}, status=400)

    try:
        dialecto = csv.Sniffer().sniff(contenido[:4096], delimiters=';,\t')
    except csv.Error:
        dialecto = csv.excel_tab
        dialecto.delimiter = '\t'

    lector = csv.DictReader(io.StringIO(contenido), dialect=dialecto)
    if not lector.fieldnames:
        return JsonResponse({'success': False, 'error': 'El archivo no tiene encabezados.'}, status=400)

    aliases = {
        'codigo_pozo': ['codigo pozo'],
        'nombre': ['nombre lugar', 'nombre', 'lugar'],
        'x': ['x', 'longitud x', 'lon', 'longitude'],
        'y': ['y', 'latitud y', 'lat', 'latitude'],
        'fecha_toma': ['fecha muestreo', 'fecha toma', 'fecha'],
        'n_amoniaca': ['n amoniacal mg l', 'n amoniacal'],
        'nitritos': ['n nitritos mg l', 'n nitritos', 'nitritos'],
        'nitratos': ['n nitratos mg l', 'n nitratos', 'nitratos'],
        'alcalinida': ['alcalinidad total mg l', 'alcalinidad total', 'alcalinidad'],
        'materia_or': ['materia organica mg l', 'materia organica'],
        'conductivi': ['conductividad us cm', 'conductividad'],
        'ph': ['ph'],
        'bicarbonat': ['bicarbonato mg l', 'bicarbonato'],
        'carbonatos': ['carbonato mg l', 'carbonato'],
        'sulfatos': ['sulfato mg l', 'sulfato'],
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
        'col_fecale': ['coliformes fecales ufc 100 ml', 'coliformes fecales', 'coliformes']
    }

    filas = [
        {normalizar_columna(k): v for k, v in fila.items() if k is not None}
        for fila in lector
    ]

    if not filas:
        return JsonResponse({'success': False, 'error': 'El archivo estÃ¡ vacÃ­o.'}, status=400)

    insertados = 0
    errores = []

    with transaction.atomic():
        for idx, fila in enumerate(filas, start=2):
            try:
                x = parsear_decimal(valor_csv(fila, aliases, 'x'))
                y = parsear_decimal(valor_csv(fila, aliases, 'y'))

                if x is None or y is None:
                    errores.append(f'Fila {idx}: coordenadas x/y invÃ¡lidas.')
                    continue

                geom = Point(x, y, srid=srid_origen)
                if srid_origen != 4326:
                    geom.transform(4326)

                Muestreo.objects.create(
                    estacionid=(valor_csv(fila, aliases, 'codigo_pozo') or None),
                    nombre=(valor_csv(fila, aliases, 'nombre') or None),
                    fecha_toma=(valor_csv(fila, aliases, 'fecha_toma') or None),
                    longitud_x=x,
                    latitud_y=y,
                    grupo=grupo,
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
                    user=request.user
                )
                insertados += 1
            except Exception as e:
                errores.append(f'Fila {idx}: {e}')

    if insertados == 0:
        return JsonResponse({'success': False, 'error': 'No se insertÃ³ ningÃºn punto.', 'detalles': errores[:10]}, status=400)

    return JsonResponse({
        'success': True,
        'insertados': insertados,
        'omitidos': len(filas) - insertados,
        'errores': errores[:10]
    })


@require_POST
@login_required
@csrf_protect
def cambiar_publicacion_grupo_puntos(request):
    """Cambia el estado público de un grupo de puntos del usuario actual."""
    try:
        data = json.loads(request.body)
        grupo = (data.get('grupo') or '').strip()
        publico = bool(data.get('publico'))

        if not grupo:
            return JsonResponse({'success': False, 'error': 'Grupo inválido.'}, status=400)

        actualizados = Muestreo.objects.filter(
            user=request.user,
            grupo=grupo
        ).update(publico=publico)

        if actualizados == 0:
            return JsonResponse({'success': False, 'error': 'No se encontraron puntos propios para ese grupo.'}, status=404)

        return JsonResponse({'success': True, 'grupo': grupo, 'publico': publico, 'actualizados': actualizados})
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

        actualizados = Muestreo.objects.filter(
            user=request.user,
            grupo=grupo_actual
        ).update(grupo=grupo_nuevo)

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
def eliminar_punto_view(request, id):
    """Elimina un punto de muestreo si pertenece al usuario actual."""
    try:
        punto = Muestreo.objects.get(gid=id, user=request.user)
        punto.delete()
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

                Capa.objects.create(
                    wkb_geometry=geom,
                    user=request.user,
                    nombre=nombre
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
            capa.delete()
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
    capa.user = None
    capa.save(update_fields=['user'])
    return JsonResponse({'success': True})


@login_required
def mis_capas_list_json(request):
    """Lista solo las capas propias del usuario logueado."""
    capas = Capa.objects.filter(user=request.user).order_by('-fecha_subida')
    results = [{
        'id': c.ogc_fid,
        'nombre': c.nombre or 'Sin nombre',
        'descripcion': c.descripcion or '',
        'estado': c.estado,
        'fecha_subida': c.fecha_subida.isoformat(),
    } for c in capas]
    return JsonResponse({'results': results})


@require_POST
@login_required
def solicitar_publicacion(request, capa_id):
    """Marca una capa como pendiente de publicación."""
    try:
        capa = Capa.objects.get(pk=capa_id, user=request.user)
        capa.estado = 'pendiente'
        capa.save(update_fields=['estado'])
        return JsonResponse({'success': True})
    except Capa.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No encontrado'}, status=404)


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
    raster.delete()
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
    group = get_or_create_map_admin_group()
    target.groups.add(group)
    target.is_staff = True
    target.save()
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
    group = get_or_create_map_admin_group()
    target.groups.remove(group)
    if not target.is_superuser and not target.groups.filter(name=group.name).exists():
        target.is_staff = False
    target.save()
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
        with connection.cursor() as cur:
            cur.execute("""
                UPDATE patino
                SET user_id = %s
                WHERE user_id IS NULL
                AND fecha_subida IS NULL
            """, [request.user.id])

        return JsonResponse({
            'success': True,
            'mensaje': 'Capa Shapefile cargada correctamente'
        })

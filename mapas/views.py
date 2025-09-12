# mapas/views.py
"""
Vistas principales del visor del Acuífero Patiño.
Incluye autenticación, gestión de puntos de muestreo, capas, y administración de usuarios.
"""

from django.shortcuts import render, redirect
from django.core.serializers import serialize
from django.db import transaction, connection
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt, csrf_protect

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, GEOSGeometry, MultiPolygon

import json

from .forms import CustomLoginForm
from .models import Muestreo, Capa, PreferenciasMapa
from .roles import is_map_admin, get_or_create_map_admin_group


# =========================
# Helpers
# =========================
def es_admin(user):
    """Devuelve True si el usuario es staff o pertenece al grupo map_admin."""
    return user.is_authenticated and (
        user.is_staff or user.groups.filter(name='map_admin').exists()
    )


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
        muestreos_qs = Muestreo.objects.filter(Q(user=request.user) | Q(user__isnull=True))
        capas_qs = Capa.objects.filter(Q(user=request.user) | Q(user__isnull=True))
        try:
            pref = PreferenciasMapa.objects.get(user=request.user)
            centro_mapa = {'lat': pref.centro_mapa.y, 'lng': pref.centro_mapa.x}
        except PreferenciasMapa.DoesNotExist:
            centro_mapa = None
    else:
        muestreos_qs = Muestreo.objects.filter(user__isnull=True)
        capas_qs = Capa.objects.filter(user__isnull=True)
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

    return render(request, 'mapas/mapa_muestreo.html', {
        'muestreos': muestreos,
        'patino': json.dumps(capas_fc),
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
            punto = Muestreo(
                nombre=data.get('nombre'),
                fecha_toma=data.get('fecha_toma'),
                nitratos=data.get('nitratos') or None,
                ph=data.get('ph') or None,
                conductivi=data.get('conductivi') or None,
                arsenico=data.get('arsenico') or None,
                col_fecale=data.get('col_fecale') or None,
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

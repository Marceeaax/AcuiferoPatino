from django.shortcuts import render, redirect
from django.core.serializers import serialize
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from .models import Muestreo, Capa
from .forms import CustomLoginForm
from .models import PreferenciasMapa
from django.views.decorators.http import require_GET


def es_admin(user):
    # staff o miembro del grupo 'map_admin'
    return user.is_authenticated and (
        user.is_staff or user.groups.filter(name='map_admin').exists()
    )

def mapa_muestreo_view(request):
    if request.user.is_authenticated:
        muestreos_qs = Muestreo.objects.filter(Q(user=request.user) | Q(user__isnull=True))
        # 👇 incluir públicas (user IS NULL) + propias
        capas_qs = Capa.objects.filter(Q(user=request.user) | Q(user__isnull=True))
        try:
            pref = PreferenciasMapa.objects.get(user=request.user)
            centro_mapa = {'lat': pref.centro_mapa.y, 'lng': pref.centro_mapa.x}
        except PreferenciasMapa.DoesNotExist:
            centro_mapa = None
    else:
        muestreos_qs = Muestreo.objects.filter(user__isnull=True)
        # 👇 anónimos ven las públicas
        capas_qs = Capa.objects.filter(user__isnull=True)
        centro_mapa = None

    muestreos = serialize('geojson', muestreos_qs, geometry_field='geom',
                          fields=['id'] + [f.name for f in Muestreo._meta.fields if f.name != 'geom'])

    capas = serialize('geojson', capas_qs, geometry_field='wkb_geometry',
                      fields=['id','nombre','descripcion'])

    return render(request, 'mapas/mapa_muestreo.html', {
        'muestreos': muestreos,
        'patino': capas,        # <-- aquí llegan las 2 features
        'centro_mapa': centro_mapa,
        'es_admin': es_admin(request.user)
    })

def login_view(request):
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
    logout(request)
    return redirect('login')

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'mapas/register.html', {'form': form})

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from django.contrib.gis.geos import Point
from .models import PreferenciasMapa

@csrf_exempt
@login_required
def guardar_centro_mapa(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            lat = data.get('lat')
            lng = data.get('lng')

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

@csrf_exempt
@login_required
def guardar_nuevo_punto(request):
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
            print(data)
            punto.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

@require_POST
@login_required
@csrf_protect
def eliminar_punto_view(request, id):
    try:
        punto = Muestreo.objects.get(gid=id, user=request.user)
        punto.delete()
        return JsonResponse({'success': True})
    except Muestreo.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Punto no encontrado o no autorizado'})


from django.views.decorators.http import require_POST
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.contrib.gis.gdal import DataSource
from django.http import JsonResponse
from .models import Capa
from django.db import transaction
import json

@require_POST
@login_required
def cargar_capa_patino(request):
    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'success': False, 'error': 'Archivo no recibido'}, status=400)

    try:
        # Leer el archivo completo (UploadedFile es file-like)
        data = json.load(archivo)
    except json.JSONDecodeError as e:
        return JsonResponse({'success': False, 'error': f'Error de sintaxis en el GeoJSON: {e}'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

    # Normalizar a una lista de "features" para procesar
    features = []
    gtype = data.get("type")

    if gtype == "FeatureCollection":
        features = data.get("features", [])
    elif gtype == "Feature":
        features = [data]
    elif "type" in data and "coordinates" in data:
        # Es una Geometry pura
        features = [{"type": "Feature", "properties": {}, "geometry": data}]
    else:
        return JsonResponse({'success': False, 'error': 'Estructura GeoJSON no reconocida.'}, status=400)

    insertados = 0
    errores = []

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
                    errores.append(f'Feature #{i}: tipo {geom.geom_type} no soportado (solo Polygon/MultiPolygon).')
                    continue

                props = feat.get("properties", {}) or {}
                nombre = props.get("name") or props.get("Nombre") or "Sin nombre"

                Capa.objects.create(
                    wkb_geometry=geom,
                    user=request.user,       # ← quedará con Marcelo (id=3) si estás logueado como él
                    nombre=nombre
                )
                insertados += 1

            except Exception as e:
                errores.append(f'Feature #{i}: {e}')

    if insertados == 0:
        return JsonResponse({
            'success': False,
            'error': 'No se insertó ninguna geometría.',
            'detalles': errores[:5]  # muestra los primeros errores para no saturar
        }, status=400)

    return JsonResponse({
        'success': True,
        'insertados': insertados,
        'omitidos': len(features) - insertados,
        'errores': errores[:5]
    })

from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.http import JsonResponse, Http404
from .roles import is_map_admin, get_or_create_map_admin_group

@require_POST
@login_required
@user_passes_test(is_map_admin)
def make_admin(request, user_id):
    # Solo un admin existente (o superuser) puede promover a otro
    try:
        target = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        raise Http404("Usuario no encontrado")

    group = get_or_create_map_admin_group()
    target.groups.add(group)
    # (opcional) darle acceso al admin site
    target.is_staff = True
    target.save()

    return JsonResponse({"success": True, "message": f"{target.username} ahora es administrador"})

@require_POST
@login_required
@user_passes_test(is_map_admin)
def remove_admin(request, user_id):
    try:
        target = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        raise Http404("Usuario no encontrado")

    group = get_or_create_map_admin_group()
    target.groups.remove(group)
    # (opcional) retirar acceso al admin site si no pertenece a otros grupos que lo requieran
    if not target.is_superuser and not target.groups.filter(name=group.name).exists():
        # si ya no tiene el grupo, podés decidir dejar is_staff como está o bajarlo:
        target.is_staff = False
    target.save()

    return JsonResponse({"success": True, "message": f"{target.username} ya no es administrador"})

@require_GET
@login_required
def usuarios_list_json(request):
    if not es_admin(request.user):
        return JsonResponse({'detail': 'No autorizado'}, status=403)

    users = (User.objects
             .exclude(id=request.user.id)    # ← excluir logueado
             .order_by('id')
             .prefetch_related('groups'))

    results = []
    for u in users:
        results.append({
            'id': u.id,
            'username': u.username,
            'email': u.email or '',
            'groups': [g.name for g in u.groups.all()],
            'is_staff': u.is_staff,
            'is_superuser': u.is_superuser,
            'last_login': u.last_login.isoformat() if u.last_login else None,
            'date_joined': u.date_joined.isoformat() if u.date_joined else None,
        })
    return JsonResponse({'results': results})
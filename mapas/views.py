from django.shortcuts import render, redirect
from django.core.serializers import serialize
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from .models import Muestreo, Patino
from .forms import CustomLoginForm
from .models import PreferenciasMapa

def mapa_muestreo_view(request):
    if request.user.is_authenticated:
        muestreos_qs = Muestreo.objects.filter(Q(user=request.user) | Q(user__isnull=True))
        try:
            pref = PreferenciasMapa.objects.get(user=request.user)
            centro_mapa = {'lat': pref.centro_mapa.y, 'lng': pref.centro_mapa.x}
        except PreferenciasMapa.DoesNotExist:
            centro_mapa = None
    else:
        muestreos_qs = Muestreo.objects.filter(user__isnull=True)
        centro_mapa = None

    muestreos = serialize(
        'geojson',
        muestreos_qs,
        geometry_field='geom',
        fields=['id'] + [f.name for f in Muestreo._meta.fields if f.name != 'geom']
    )

    patino = serialize('geojson', Patino.objects.all(), geometry_field='wkb_geometry')

    return render(request, 'mapas/mapa_muestreo.html', {
        'muestreos': muestreos,
        'patino': patino,
        'centro_mapa': centro_mapa
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


from django.shortcuts import render
from django.core.serializers import serialize
from .models import Muestreo, Patino
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.forms import AuthenticationForm
from .forms import CustomLoginForm


def mapa_muestreo_view(request):
    muestreos = serialize(
    'geojson',
    Muestreo.objects.all(),
    geometry_field='geom',
    fields=[f.name for f in Muestreo._meta.fields if f.name != 'geom']
    )
    print(muestreos)

    patino = serialize('geojson', Patino.objects.all(), geometry_field='wkb_geometry')

    return render(request, 'mapas/mapa_muestreo.html', {
        'muestreos': muestreos,
        'patino': patino
    })

def login_view(request):
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('mapa_muestreo')
    else:
        form = CustomLoginForm()
    return render(request, 'mapas/login.html', {'form': form})



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
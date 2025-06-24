from django.urls import path
from . import views
from .views import mapa_muestreo_view
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('mapa-muestreo/', mapa_muestreo_view, name='mapa_muestreo'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('guardar-centro/', views.guardar_centro_mapa, name='guardar_centro'),
    path('guardar-nuevo-punto/', views.guardar_nuevo_punto, name='guardar_nuevo_punto'),
    path('eliminar-punto/<int:id>/', views.eliminar_punto_view, name='eliminar_punto'),

]

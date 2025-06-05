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
]

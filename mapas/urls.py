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
    path('editar-punto/<int:id>/', views.editar_punto_view, name='editar_punto'),
    path('descargas/puntos/', views.descargar_puntos, name='descargar_puntos'),
    path('descargas/capas/<int:ogc_fid>/', views.descargar_capa_geojson, name='descargar_capa_geojson'),
    path('descargas/rasters/<int:raster_id>/', views.descargar_raster, name='descargar_raster'),
    path('cargar-puntos-csv/', views.cargar_puntos_csv, name='cargar_puntos_csv'),
    path('puntos/grupo-publico/', views.cambiar_publicacion_grupo_puntos, name='cambiar_publicacion_grupo_puntos'),
    path('puntos/grupo-renombrar/', views.renombrar_grupo_puntos, name='renombrar_grupo_puntos'),
    path('eliminar-punto/<int:id>/', views.eliminar_punto_view, name='eliminar_punto'),
    path('preview-capa-tiff/', views.preview_capa_tiff, name='preview_capa_tiff'),
    path('cargar-capa-tiff/', views.cargar_capa_tiff, name='cargar_capa_tiff'),
    path('eliminar-capa-tiff/<int:raster_id>/', views.eliminar_capa_tiff, name='eliminar_capa_tiff'),
    path('cargar-capa-patino/', views.cargar_capa_patino, name='cargar_capa_patino'),
    path('cargar-capa-shapefile/', views.cargar_capa_shapefile, name='cargar_capa_shapefile'),
    path("usuarios/<int:user_id>/make-admin/", views.make_admin, name="make_admin"),
    path("usuarios/<int:user_id>/remove-admin/", views.remove_admin, name="remove_admin"),
    path('api/usuarios/', views.usuarios_list_json, name='usuarios_list_json'),
    path('eliminar-capa/<int:ogc_fid>/', views.eliminar_capa_view, name='eliminar_capa'),
    path('api/capas/', views.capas_list_json,name='api_capas'),
    path('api/solicitudes-publicacion/', views.solicitudes_publicacion_list_json, name='solicitudes_publicacion_list_json'),
    path('api/solicitudes-publicacion/<int:solicitud_id>/resolver/', views.resolver_solicitud_publicacion, name='resolver_solicitud_publicacion'),
    path('capas/<int:ogc_fid>/hacer-publica/', views.hacer_publica_view, name='capa_hacer_publica'),
    path("api/mis-capas/", views.mis_capas_list_json, name="mis_capas_list_json"),
    path("api/solicitar-publicacion/<int:capa_id>/", views.solicitar_publicacion, name="solicitar_publicacion"),
    path("eliminar-capa/<int:ogc_fid>/", views.eliminar_capa_view, name="eliminar_capa")
]

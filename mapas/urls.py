from django.urls import path, reverse_lazy
from . import views
from .views import mapa_muestreo_view
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('mapa-muestreo/', mapa_muestreo_view, name='mapa_muestreo'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path(
        'password_reset/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.txt',
            subject_template_name='registration/password_reset_subject.txt',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password_reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    path('guardar-centro/', views.guardar_centro_mapa, name='guardar_centro'),
    path('guardar-visibilidad-capas/', views.guardar_visibilidad_capas, name='guardar_visibilidad_capas'),
    path('guardar-nuevo-punto/', views.guardar_nuevo_punto, name='guardar_nuevo_punto'),
    path('editar-punto/<int:id>/', views.editar_punto_view, name='editar_punto'),
    path('descargas/puntos/', views.descargar_puntos, name='descargar_puntos'),
    path('descargas/capas/<int:ogc_fid>/', views.descargar_capa_geojson, name='descargar_capa_geojson'),
    path('descargas/rasters/<int:raster_id>/', views.descargar_raster, name='descargar_raster'),
    path('preview-puntos-tabular/', views.preview_puntos_tabular, name='preview_puntos_tabular'),
    path('cargar-puntos-csv/', views.cargar_puntos_csv, name='cargar_puntos_csv'),
    path('puntos/grupo-publico/', views.cambiar_publicacion_grupo_puntos, name='cambiar_publicacion_grupo_puntos'),
    path('puntos/grupo-actividad/', views.cambiar_actividad_grupo_puntos, name='cambiar_actividad_grupo_puntos'),
    path('puntos/grupo-publico-admin/', views.hacer_publico_grupo_puntos_admin, name='hacer_publico_grupo_puntos_admin'),
    path('puntos/grupo-renombrar/', views.renombrar_grupo_puntos, name='renombrar_grupo_puntos'),
    path('puntos/grupo-eliminar/', views.eliminar_grupo_puntos, name='eliminar_grupo_puntos'),
    path('eliminar-punto/<int:id>/', views.eliminar_punto_view, name='eliminar_punto'),
    path('preview-capa-tiff/', views.preview_capa_tiff, name='preview_capa_tiff'),
    path('cargar-capa-tiff/', views.cargar_capa_tiff, name='cargar_capa_tiff'),
    path('eliminar-capa-tiff/<int:raster_id>/', views.eliminar_capa_tiff, name='eliminar_capa_tiff'),
    path('capas-raster/<int:raster_id>/hacer-publica/', views.hacer_publica_capa_tiff_admin, name='hacer_publica_capa_tiff_admin'),
    path('capas-raster/<int:raster_id>/actividad/', views.cambiar_actividad_raster_view, name='cambiar_actividad_raster'),
    path('cargar-capa-patino/', views.cargar_capa_patino, name='cargar_capa_patino'),
    path('cargar-capa-shapefile/', views.cargar_capa_shapefile, name='cargar_capa_shapefile'),
    path("usuarios/<int:user_id>/make-admin/", views.make_admin, name="make_admin"),
    path("usuarios/<int:user_id>/remove-admin/", views.remove_admin, name="remove_admin"),
    path('api/usuarios/', views.usuarios_list_json, name='usuarios_list_json'),
    path('eliminar-capa/<int:ogc_fid>/', views.eliminar_capa_view, name='eliminar_capa'),
    path('capas/<int:ogc_fid>/actividad/', views.cambiar_actividad_capa_view, name='cambiar_actividad_capa'),
    path('api/capas/', views.capas_admin_dashboard_json,name='api_capas'),
    path('api/solicitudes-publicacion/', views.solicitudes_publicacion_list_json, name='solicitudes_publicacion_list_json'),
    path('api/solicitudes-publicacion/<int:solicitud_id>/resolver/', views.resolver_solicitud_publicacion, name='resolver_solicitud_publicacion'),
    path('api/solicitudes-registro/<int:solicitud_id>/resolver/', views.resolver_solicitud_registro, name='resolver_solicitud_registro'),
    path('capas/<int:ogc_fid>/hacer-publica/', views.hacer_publica_view, name='capa_hacer_publica'),
    path("api/mis-capas/", views.mis_capas_list_json, name="mis_capas_list_json"),
    path("api/solicitar-publicacion/<int:capa_id>/", views.solicitar_publicacion, name="solicitar_publicacion"),
    path("eliminar-capa/<int:ogc_fid>/", views.eliminar_capa_view, name="eliminar_capa")
]

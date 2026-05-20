import inspect
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase

from . import views
from .models import PreferenciasMapa, SolicitudPublicacion


class HelperFunctionsTests(SimpleTestCase):
    def test_normalizar_columna_elimina_acentos_y_simbolos(self):
        valor = views.normalizar_columna("N-Nitratos (mg/L)")
        self.assertEqual(valor, "n nitratos mg l")

    def test_parsear_decimal_acepta_coma_y_miles(self):
        self.assertEqual(views.parsear_decimal("1.234,56"), 1234.56)
        self.assertEqual(views.parsear_decimal("123,45"), 123.45)
        self.assertIsNone(views.parsear_decimal(""))

    def test_valor_csv_busca_primer_alias_con_valor(self):
        fila = {"nombre lugar": "", "nombre": "Pozo 7"}
        aliases = {"nombre": ["nombre lugar", "nombre"]}
        self.assertEqual(views.valor_csv(fila, aliases, "nombre"), "Pozo 7")


class DownloadViewsTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("mapas.views.muestreos_visibles_qs")
    def test_descargar_puntos_csv_devuelve_attachment(self, mock_visible_qs):
        qs = MagicMock()
        qs.exists.return_value = True
        qs.__iter__.return_value = iter([
            SimpleNamespace(
                gid=1,
                estacionid="P001",
                codigoorig="ORIG",
                longitud_x="-57.5",
                latitud_y="-25.3",
                nombre="Pozo 1",
                entidad="ESSAP",
                fecha_toma="2026-05-20",
                alcalinida=None,
                bicarbonat=None,
                calcio=None,
                carbonatos=None,
                cloruro=None,
                col_fecale=None,
                conductivi=120,
                dureza_tot=None,
                hierro_tot=None,
                magnesio=10,
                n_amoniaca=None,
                nitratos=12,
                nitritos=0.1,
                ph=7.1,
                potasio=None,
                sodio=None,
                std=None,
                sulfatos=None,
                temperatur=None,
                turbidez=None,
                materia_or=1.2,
                arsenico=None,
                mercurio=None,
                manganeso=None,
                cobre=None,
                cromo=None,
                dureza_cal=None,
                dureza_mag=None,
                grupo="PATINO2",
                lote_carga=None,
                archivo_origen=None,
                srid_origen=4326,
                activo=True,
                publico=True,
            )
        ])
        mock_visible_qs.return_value = qs
        request = self.factory.get("/descargas/puntos/?formato=csv")
        request.user = SimpleNamespace(is_authenticated=False)

        response = views.descargar_puntos(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment; filename="puntos_todos.csv"', response["Content-Disposition"])
        self.assertIn("Pozo 1", response.content.decode("utf-8"))

    @patch("mapas.views.serialize_points_geojson", return_value='{"type":"FeatureCollection","features":[]}')
    @patch("mapas.views.muestreos_visibles_qs")
    def test_descargar_puntos_geojson_devuelve_attachment(self, mock_visible_qs, mock_serialize):
        qs = MagicMock()
        qs.exists.return_value = True
        mock_visible_qs.return_value = qs
        request = self.factory.get("/descargas/puntos/?formato=geojson&grupo=PATINO2")
        request.user = SimpleNamespace(is_authenticated=True)

        response = views.descargar_puntos(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/geo+json")
        self.assertIn('attachment; filename="puntos_patino2.geojson"', response["Content-Disposition"])
        mock_serialize.assert_called_once_with(qs.filter.return_value)

    @patch("mapas.views.capas_visibles_qs")
    def test_descargar_capa_geojson_devuelve_feature_collection(self, mock_capas_qs):
        capa = SimpleNamespace(
            ogc_fid=7,
            nombre="Afghanistan",
            descripcion="Capa de prueba",
            user_id=None,
            wkb_geometry=SimpleNamespace(geojson='{"type":"MultiPolygon","coordinates":[]}'),
        )
        mock_capas_qs.return_value.get.return_value = capa
        request = self.factory.get("/descargas/capas/7/")
        request.user = SimpleNamespace(is_authenticated=False)

        response = views.descargar_capa_geojson(request, 7)

        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment; filename="capa_afghanistan.geojson"', response["Content-Disposition"])
        self.assertIn("Afghanistan", response.content.decode("utf-8"))


class MapaMuestreoViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("mapas.views.render")
    @patch("mapas.views.serialize")
    @patch("mapas.views._latest_request_map_for_user", return_value={})
    @patch("mapas.views.CapaRaster.objects.filter")
    @patch("mapas.views.Capa.objects.filter")
    @patch("mapas.views.Muestreo.objects.filter")
    def test_usuario_anonimo_ve_puntos_publicos_y_sin_dueno(
        self,
        mock_muestreo_filter,
        mock_capa_filter,
        mock_raster_filter,
        _mock_latest_requests,
        mock_serialize,
        mock_render,
    ):
        request = self.factory.get("/mapa-muestreo/")
        request.user = SimpleNamespace(is_authenticated=False)

        mock_muestreo_qs = Mock(name="muestreos_qs")
        mock_muestreo_filter.return_value.distinct.return_value = mock_muestreo_qs

        mock_capa_filter.return_value = []
        mock_raster_filter.return_value = []
        mock_serialize.return_value = '{"type":"FeatureCollection","features":[]}'
        mock_render.return_value = HttpResponse("ok")

        response = views.mapa_muestreo_view(request)

        self.assertEqual(response.status_code, 200)
        mock_muestreo_filter.assert_called_once()
        _, kwargs = mock_muestreo_filter.call_args
        self.assertTrue(kwargs["activo"])
        mock_capa_filter.assert_called_once_with(user__isnull=True)

        contexto = mock_render.call_args.args[2]
        self.assertEqual(contexto["centro_mapa"], None)
        self.assertFalse(contexto["es_admin"])

    @patch("mapas.views.render")
    @patch("mapas.views.serialize")
    @patch("mapas.views._latest_request_map_for_user", return_value={})
    @patch("mapas.views.PreferenciasMapa.objects.get")
    @patch("mapas.views.CapaRaster.objects.filter")
    @patch("mapas.views.Capa.objects.filter")
    @patch("mapas.views.Muestreo.objects.filter")
    def test_usuario_autenticado_recibe_centro_preferido(
        self,
        mock_muestreo_filter,
        mock_capa_filter,
        mock_raster_filter,
        mock_pref_get,
        _mock_latest_requests,
        mock_serialize,
        mock_render,
    ):
        request = self.factory.get("/mapa-muestreo/")
        request.user = SimpleNamespace(
            id=9,
            is_authenticated=True,
            is_staff=False,
            groups=SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(exists=lambda: False)),
        )

        mock_muestreo_qs = Mock(name="muestreos_qs")
        mock_muestreo_filter.return_value.distinct.return_value = mock_muestreo_qs
        mock_capa_filter.return_value = []
        mock_raster_filter.return_value = []
        mock_pref_get.return_value = SimpleNamespace(
            centro_mapa=SimpleNamespace(x=-57.5, y=-25.3)
        )
        mock_serialize.return_value = '{"type":"FeatureCollection","features":[]}'
        mock_render.return_value = HttpResponse("ok")

        response = views.mapa_muestreo_view(request)

        self.assertEqual(response.status_code, 200)
        contexto = mock_render.call_args.args[2]
        self.assertEqual(contexto["centro_mapa"], {"lat": -25.3, "lng": -57.5})
        self.assertFalse(contexto["es_admin"])

    @patch("mapas.views.render")
    @patch("mapas.views.serialize")
    @patch("mapas.views.SolicitudPublicacion.objects.filter")
    @patch("mapas.views._latest_request_map_for_user", return_value={})
    @patch("mapas.views.PreferenciasMapa.objects.get", side_effect=views.PreferenciasMapa.DoesNotExist)
    @patch("mapas.views.CapaRaster.objects.filter")
    @patch("mapas.views.Capa.objects.filter")
    @patch("mapas.views.Muestreo.objects.filter")
    def test_muestreos_geojson_incluye_nombres_de_auditoria(
        self,
        mock_muestreo_filter,
        mock_capa_filter,
        mock_raster_filter,
        _mock_pref_get,
        _mock_latest_requests,
        mock_request_filter,
        mock_serialize,
        mock_render,
    ):
        request = self.factory.get("/mapa-muestreo/")
        request.user = SimpleNamespace(
            id=9,
            is_authenticated=True,
            is_staff=True,
            groups=SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(exists=lambda: True)),
        )

        mock_muestreo_qs = Mock(name="muestreos_qs")
        mock_muestreo_qs.values.return_value = [
            {
                "gid": 15,
                "usu_insercion__username": "marce",
                "usu_modificacion__username": "liz",
            }
        ]
        mock_muestreo_filter.return_value.distinct.return_value = mock_muestreo_qs
        mock_capa_filter.return_value = []
        mock_raster_filter.return_value = []
        mock_request_filter.return_value.count.return_value = 0
        mock_serialize.return_value = json.dumps({
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "15",
                    "type": "Feature",
                    "properties": {"nombre": "Pozo 15", "usu_insercion": 3, "usu_modificacion": 5},
                    "geometry": None,
                }
            ],
        })
        mock_render.return_value = HttpResponse("ok")

        response = views.mapa_muestreo_view(request)
        contexto = mock_render.call_args.args[2]
        muestreos = json.loads(contexto["muestreos"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(muestreos["features"][0]["properties"]["usu_insercion_nombre"], "marce")
        self.assertEqual(muestreos["features"][0]["properties"]["usu_modificacion_nombre"], "liz")

    @patch("mapas.views.render")
    @patch("mapas.views.serialize")
    @patch("mapas.views._latest_request_map_for_user", return_value={})
    @patch("mapas.views.PreferenciasMapa.objects.get", side_effect=views.PreferenciasMapa.DoesNotExist)
    @patch("mapas.views.CapaRaster.objects.filter")
    @patch("mapas.views.Capa.objects.filter")
    @patch("mapas.views.Muestreo.objects.filter")
    def test_geojson_de_capas_marca_propias_y_publicas(
        self,
        mock_muestreo_filter,
        mock_capa_filter,
        mock_raster_filter,
        _mock_pref_get,
        _mock_latest_requests,
        mock_serialize,
        mock_render,
    ):
        request = self.factory.get("/mapa-muestreo/")
        request.user = SimpleNamespace(
            id=9,
            is_authenticated=True,
            is_staff=False,
            groups=SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(exists=lambda: False)),
        )

        mock_muestreo_filter.return_value.distinct.return_value = Mock(name="muestreos_qs")
        mock_serialize.return_value = '{"type":"FeatureCollection","features":[]}'
        mock_raster_filter.return_value = []
        mock_capa_filter.return_value = [
            SimpleNamespace(
                ogc_fid=1,
                nombre="Capa publica",
                descripcion="Visible para todos",
                user_id=None,
                estado="publica",
                wkb_geometry=SimpleNamespace(geojson='{"type":"MultiPolygon","coordinates":[]}'),
            ),
            SimpleNamespace(
                ogc_fid=2,
                nombre="Capa propia",
                descripcion="Solo mia",
                user_id=9,
                estado="privada",
                wkb_geometry=SimpleNamespace(geojson='{"type":"MultiPolygon","coordinates":[]}'),
            ),
        ]
        mock_render.return_value = HttpResponse("ok")

        response = views.mapa_muestreo_view(request)
        contexto = mock_render.call_args.args[2]
        capas = json.loads(contexto["patino"])["features"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(capas), 2)
        self.assertTrue(capas[0]["properties"]["es_publica"])
        self.assertFalse(capas[0]["properties"]["es_propia"])
        self.assertFalse(capas[1]["properties"]["es_publica"])
        self.assertTrue(capas[1]["properties"]["es_propia"])


class CargarPuntosCsvTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.cargar_puntos_csv)
        self.user = SimpleNamespace(id=7, is_authenticated=True)

    def _request_csv(self, contenido, grupo="PATINO2", srid="32721", filename="muestreo.csv"):
        payload = contenido.encode("utf-8") if isinstance(contenido, str) else contenido
        archivo = SimpleUploadedFile(
            filename,
            payload,
            content_type="text/csv",
        )
        request = self.factory.post(
            "/cargar-puntos-csv/",
            data={"grupo": grupo, "srid": srid, "archivo": archivo},
        )
        request.user = self.user
        return request

    @patch("mapas.views.transaction.atomic", side_effect=lambda: nullcontext())
    @patch("mapas.views.Muestreo.objects.create")
    @patch("mapas.views.Point")
    def test_carga_csv_inserta_filas_validas_y_asigna_grupo(
        self,
        mock_point,
        mock_create,
        _mock_atomic,
    ):
        geom = Mock()
        geom.x = -57.6012
        geom.y = -25.3001
        mock_point.return_value = geom

        request = self._request_csv(
            "codigo_pozo;nombre_lugar;x;y;Fecha_muestreo;N-Nitratos (mg/L);pH\n"
            "01;Pozo A;444842,95;7196078,49;22-06-2018;95,8;5,7\n"
            "02;Pozo B;443455,38;7194145,98;22-06-2018;96,3;5,97\n"
        )

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["insertados"], 2)
        self.assertEqual(mock_create.call_count, 2)
        self.assertEqual(mock_create.call_args.kwargs["grupo"], "PATINO2")
        self.assertEqual(mock_create.call_args.kwargs["longitud_x"], -57.6012)
        self.assertEqual(mock_create.call_args.kwargs["latitud_y"], -25.3001)
        self.assertEqual(mock_create.call_args.kwargs["srid_origen"], 32721)
        self.assertEqual(mock_create.call_args.kwargs["archivo_origen"], "muestreo.csv")
        self.assertIsNotNone(mock_create.call_args.kwargs["lote_carga"])
        self.assertEqual(mock_create.call_args.kwargs["usu_insercion"], self.user)
        self.assertEqual(mock_create.call_args.kwargs["usu_modificacion"], self.user)
        geom.transform.assert_called_with(4326)

    @patch("mapas.views.transaction.atomic", side_effect=lambda: nullcontext())
    @patch("mapas.views.Muestreo.objects.create")
    @patch("mapas.views.Point")
    def test_carga_csv_omite_filas_sin_coordenadas_validas(
        self,
        mock_point,
        mock_create,
        _mock_atomic,
    ):
        mock_point.return_value = Mock()
        request = self._request_csv(
            "codigo_pozo;nombre_lugar;x;y\n"
            "01;Pozo A;;7196078,49\n"
            "02;Pozo B;443455,38;7194145,98\n"
        )

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["insertados"], 1)
        self.assertEqual(data["omitidos"], 1)
        self.assertEqual(mock_create.call_count, 1)

    def test_carga_csv_rechaza_srid_no_permitido(self):
        request = self._request_csv(
            "codigo_pozo;nombre_lugar;x;y\n"
            "01;Pozo A;444842,95;7196078,49\n",
            srid="3857",
        )

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])

    @patch("mapas.views.transaction.atomic", side_effect=lambda: nullcontext())
    @patch("mapas.views.Muestreo.objects.create")
    @patch("mapas.views.Point")
    def test_carga_csv_acepta_encoding_cp1252(
        self,
        mock_point,
        mock_create,
        _mock_atomic,
    ):
        geom = Mock()
        geom.x = -57.55
        geom.y = -25.22
        mock_point.return_value = geom
        contenido = (
            "codigo_pozo;nombre_lugar;x;y\n"
            "01;Poz\xf3 \xc1;444842,95;7196078,49\n"
        ).encode("cp1252")
        request = self._request_csv(contenido, filename="muestreo_cp1252.csv")

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(mock_create.call_args.kwargs["nombre"], "Pozó Á")


class CambiarPublicacionGrupoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.cambiar_publicacion_grupo_puntos)
        self.user = SimpleNamespace(id=3, is_authenticated=True)

    @patch("mapas.views.SolicitudPublicacion.objects.get_or_create")
    @patch("mapas.views.Muestreo.objects.filter")
    def test_publicar_grupo_crea_solicitud_pendiente(self, mock_filter, mock_get_or_create):
        mock_filter.return_value.exists.return_value = True
        mock_get_or_create.return_value = (
            SimpleNamespace(estado=SolicitudPublicacion.ESTADO_PENDIENTE, review_comment=""),
            True,
        )
        request = self.factory.post(
            "/puntos/grupo-publico/",
            data=json.dumps({"grupo": "PATINO2", "publico": True}),
            content_type="application/json",
        )
        request.user = self.user

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_filter.assert_called_once_with(user=self.user, grupo="PATINO2")
        self.assertEqual(data["estado_solicitud"], "pendiente")
        self.assertTrue(data["solicitud_creada"])

    @patch("mapas.views.SolicitudPublicacion.objects.filter")
    @patch("mapas.views.Muestreo.objects.filter")
    def test_hacer_privado_grupo_cancela_solicitudes_pendientes(self, mock_filter, mock_requests_filter):
        mock_filter.return_value.exists.return_value = True
        mock_filter.return_value.update.return_value = 5
        request = self.factory.post(
            "/puntos/grupo-publico/",
            data=json.dumps({"grupo": "PATINO2", "publico": False}),
            content_type="application/json",
        )
        request.user = self.user

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_filter.assert_called_once_with(user=self.user, grupo="PATINO2")
        update_kwargs = mock_filter.return_value.update.call_args.kwargs
        self.assertFalse(update_kwargs["publico"])
        self.assertEqual(update_kwargs["usu_modificacion_id"], self.user.id)
        self.assertIsNotNone(update_kwargs["fec_modificacion"])
        mock_requests_filter.assert_called_once()
        mock_requests_filter.return_value.delete.assert_called_once()


class RenombrarGrupoPuntosTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.renombrar_grupo_puntos)
        self.user = SimpleNamespace(id=3, is_authenticated=True)

    @patch("mapas.views.Muestreo.objects.filter")
    def test_renombra_grupo_propio(self, mock_filter):
        mock_filter.return_value.update.return_value = 7
        request = self.factory.post(
            "/puntos/grupo-renombrar/",
            data=json.dumps({"grupo_actual": "PATINO1", "grupo_nuevo": "PATINO2"}),
            content_type="application/json",
        )
        request.user = self.user

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_filter.assert_called_once_with(user=self.user, grupo="PATINO1")
        update_kwargs = mock_filter.return_value.update.call_args.kwargs
        self.assertEqual(update_kwargs["grupo"], "PATINO2")
        self.assertEqual(update_kwargs["usu_modificacion_id"], self.user.id)
        self.assertIsNotNone(update_kwargs["fec_modificacion"])

    @patch("mapas.views.Muestreo.objects.filter")
    def test_renombrar_grupo_falla_si_no_hay_puntos_propios(self, mock_filter):
        mock_filter.return_value.update.return_value = 0
        request = self.factory.post(
            "/puntos/grupo-renombrar/",
            data=json.dumps({"grupo_actual": "PATINO1", "grupo_nuevo": "PATINO2"}),
            content_type="application/json",
        )
        request.user = self.user

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(data["success"])


class CapaTiffTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.preview_view = inspect.unwrap(views.preview_capa_tiff)
        self.upload_view = inspect.unwrap(views.cargar_capa_tiff)
        self.delete_view = inspect.unwrap(views.eliminar_capa_tiff)
        self.user = SimpleNamespace(id=5, is_authenticated=True)

    def _workspace_tempdir(self, name):
        base = Path("C:/Users/marce/tesis/.tmp_tests") / name
        if base.exists():
            import shutil
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)
        return base

    @patch("mapas.views._resumen_raster")
    @patch("mapas.views._gdalinfo_json")
    @patch("mapas.views._ensure_raster_dirs")
    def test_preview_tiff_devuelve_metadatos_y_token(self, mock_dirs, mock_gdalinfo, mock_resumen):
        base = self._workspace_tempdir("preview_tiff")
        dirs = {
            "tmp": base / "tmp",
            "source": base / "source",
            "processed": base / "processed",
            "png": base / "png",
        }
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        mock_dirs.return_value = dirs
        mock_gdalinfo.return_value = {"bands": [{}]}
        mock_resumen.return_value = {"size": [399, 500], "band_count": 1}

        archivo = SimpleUploadedFile("demo.tif", b"fake-tiff", content_type="image/tiff")
        request = self.factory.post("/preview-capa-tiff/", data={"archivo": archivo})
        request.user = self.user

        response = self.preview_view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertIn("token", data)
        self.assertEqual(data["preview"]["band_count"], 1)

    @patch("mapas.views.CapaRaster.objects.create")
    @patch("mapas.views._procesar_raster")
    @patch("mapas.views._ensure_raster_dirs")
    def test_cargar_tiff_guarda_capa_raster(self, mock_dirs, mock_procesar, mock_create):
        media_root = self._workspace_tempdir("upload_tiff")
        dirs = {
            "tmp": media_root / "rasters" / "tmp",
            "source": media_root / "rasters" / "source",
            "processed": media_root / "rasters" / "processed",
            "png": media_root / "rasters" / "png",
        }
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        temp_tif = dirs["tmp"] / "token123.tif"
        temp_tif.write_bytes(b"fake-tiff")

        mock_dirs.return_value = dirs
        mock_procesar.return_value = {
            "processed_tif": dirs["processed"] / "demo_4326.tif",
            "png_path": dirs["png"] / "demo.png",
            "colored_tif": dirs["processed"] / "demo_colored.tif",
            "color_map": dirs["tmp"] / "demo_colormap.txt",
            "bounds": [[-25.4, -57.7], [-25.1, -57.3]],
            "metadata": {"size": [399, 500]},
        }
        for path in [mock_procesar.return_value["processed_tif"], mock_procesar.return_value["png_path"], mock_procesar.return_value["colored_tif"], mock_procesar.return_value["color_map"]]:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"x")
        mock_create.return_value = SimpleNamespace(id=11, nombre="Raster demo")

        with patch.object(views.settings, "MEDIA_ROOT", str(media_root)):
            request = self.factory.post(
                "/cargar-capa-tiff/",
                data={"token": "token123", "nombre": "Raster demo", "modo_despliegue": "png", "publico": "true"},
            )
            request.user = self.user
            response = self.upload_view(request)

        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_create.assert_called_once()

    @patch("mapas.views.CapaRaster.objects.get")
    def test_eliminar_tiff_borra_registro_y_archivos(self, mock_get):
        punto = Mock()
        punto.archivo_original.path = "C:/tmp/original.tif"
        punto.archivo_4326.path = "C:/tmp/procesado.tif"
        punto.archivo_png.path = "C:/tmp/demo.png"
        mock_get.return_value = punto

        request = self.factory.post("/eliminar-capa-tiff/4/")
        request.user = self.user

        with patch("mapas.views.os.path.exists", return_value=True), patch("mapas.views.os.remove") as mock_remove:
            response = self.delete_view(request, 4)

        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        punto.delete.assert_called_once()
        self.assertEqual(mock_remove.call_count, 3)


class CapaShapefileTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.cargar_capa_shapefile)
        self.user = SimpleNamespace(id=6, is_authenticated=True)

    def _workspace_shp_tmp(self):
        base = Path("C:/Users/marce/tesis/.tmp_tests/shapefile")
        if base.exists():
            import shutil
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)
        return base

    def test_rechaza_archivo_no_zip(self):
        archivo = SimpleUploadedFile("capa.geojson", b"{}", content_type="application/json")
        request = self.factory.post("/cargar-capa-shapefile/", data={"archivo": archivo})
        request.user = self.user

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])

    @patch("mapas.views.connection")
    @patch("mapas.views.subprocess.run")
    @patch("mapas.views.os.listdir")
    @patch("mapas.views.zipfile.ZipFile")
    @patch("mapas.views.tempfile.TemporaryDirectory")
    def test_carga_shapefile_zip_valido(self, mock_tmpdir, mock_zip, mock_listdir, mock_run, mock_connection):
        tmpdir = self._workspace_shp_tmp()
        mock_tmpdir.return_value.__enter__.return_value = str(tmpdir)
        mock_tmpdir.return_value.__exit__.return_value = False
        mock_listdir.return_value = ["demo.shp", "demo.shx", "demo.dbf", "demo.prj"]
        mock_connection.settings_dict = {
            "NAME": "tesisdb",
            "USER": "tesisuser",
            "PASSWORD": "tesispassword",
            "HOST": "localhost",
            "PORT": "5432",
        }
        mock_connection.cursor.return_value.__enter__.return_value = Mock()
        archivo = SimpleUploadedFile("capa.zip", b"fake-zip", content_type="application/zip")
        request = self.factory.post("/cargar-capa-shapefile/", data={"archivo": archivo})
        request.user = self.user

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_run.assert_called_once()
        self.assertIn("mensaje", data)


class EliminarPuntoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.eliminar_punto_view)
        self.user = SimpleNamespace(id=4, is_authenticated=True)

    @patch("mapas.views.Muestreo.objects.get")
    def test_elimina_punto_propio(self, mock_get):
        punto = Mock()
        mock_get.return_value = punto
        request = self.factory.post("/eliminar-punto/15/")
        request.user = self.user

        response = self.view(request, 15)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_get.assert_called_once_with(gid=15, user=self.user)
        punto.delete.assert_called_once()

    @patch("mapas.views.Muestreo.objects.get", side_effect=views.Muestreo.DoesNotExist)
    def test_rechaza_eliminacion_de_punto_ajeno_o_inexistente(self, mock_get):
        request = self.factory.post("/eliminar-punto/15/")
        request.user = self.user

        response = self.view(request, 15)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["success"])
        mock_get.assert_called_once_with(gid=15, user=self.user)


class EditarPuntoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.editar_punto_view)
        self.user = SimpleNamespace(id=4, is_authenticated=True)

    @patch("mapas.views.Muestreo.objects.get")
    def test_edita_punto_propio(self, mock_get):
        punto = Mock()
        mock_get.return_value = punto
        request = self.factory.post(
            "/editar-punto/15/",
            data=json.dumps({
                "estacionid": "PZ-15",
                "codigoorig": "INT-15",
                "nombre": "Pozo actualizado",
                "entidad": "ERSSAN",
                "fecha_toma": "2026-05-13",
                "grupo": "PATINO2",
                "n_amoniaca": "0.15",
                "nitritos": "0.04",
                "nitratos": "22.5",
                "alcalinida": "18.2",
                "materia_or": "0.8",
                "ph": "6.8",
                "conductivi": "350",
                "bicarbonat": "12.7",
                "carbonatos": "0",
                "sulfatos": "4.5",
                "magnesio": "3.2",
                "calcio": "7.1",
                "sodio": "5.4",
                "potasio": "1.3",
                "cloruro": "9.8",
                "arsenico": "",
                "mercurio": "0.0002",
                "manganeso": "0.01",
                "cobre": "0.02",
                "cromo": "0.03",
                "col_fecale": "0"
            }),
            content_type="application/json",
        )
        request.user = self.user

        response = self.view(request, 15)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_get.assert_called_once_with(gid=15, user=self.user)
        self.assertEqual(punto.estacionid, "PZ-15")
        self.assertEqual(punto.nombre, "Pozo actualizado")
        self.assertEqual(punto.grupo, "PATINO2")
        self.assertEqual(punto.nitritos, "0.04")
        self.assertEqual(punto.alcalinida, "18.2")
        self.assertEqual(punto.arsenico, None)
        self.assertEqual(punto.col_fecale, "0")
        punto.save.assert_called_once()

    @patch("mapas.views.Muestreo.objects.get", side_effect=views.Muestreo.DoesNotExist)
    def test_rechaza_edicion_de_punto_ajeno_o_inexistente(self, mock_get):
        request = self.factory.post(
            "/editar-punto/15/",
            data=json.dumps({"nombre": "No autorizado"}),
            content_type="application/json",
        )
        request.user = self.user

        response = self.view(request, 15)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(data["success"])
        mock_get.assert_called_once_with(gid=15, user=self.user)

    @patch("mapas.views.Point")
    @patch("mapas.views.Muestreo.objects.get")
    def test_editar_punto_actualiza_geom_y_coordenadas(self, mock_get, mock_point):
        punto = Mock()
        mock_get.return_value = punto
        geom = Mock()
        mock_point.return_value = geom
        request = self.factory.post(
            "/editar-punto/15/",
            data=json.dumps({
                "nombre": "Pozo movido",
                "fecha_toma": "2026-05-13",
                "grupo": "PATINO2",
                "lat": "-25.3001",
                "lng": "-57.6012"
            }),
            content_type="application/json",
        )
        request.user = self.user

        response = self.view(request, 15)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_point.assert_called_once_with(-57.6012, -25.3001)
        self.assertIs(punto.geom, geom)
        self.assertEqual(punto.longitud_x, -57.6012)
        self.assertEqual(punto.latitud_y, -25.3001)


class CargarCapaPatinoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.cargar_capa_patino)
        self.user = SimpleNamespace(id=10, is_authenticated=True)

    def _request_geojson(self, contenido):
        archivo = SimpleUploadedFile(
            "capa.geojson",
            contenido.encode("utf-8"),
            content_type="application/geo+json",
        )
        request = self.factory.post(
            "/cargar-capa-patino/",
            data={"archivo": archivo},
        )
        request.user = self.user
        return request

    @patch("mapas.views.transaction.atomic", side_effect=lambda: nullcontext())
    @patch("mapas.views.Capa.objects.create")
    @patch("mapas.views.MultiPolygon")
    @patch("mapas.views.GEOSGeometry")
    def test_carga_geojson_convierte_polygon_y_crea_capa(
        self,
        mock_geos,
        mock_multi,
        mock_create,
        _mock_atomic,
    ):
        polygon = Mock()
        polygon.geom_type = "Polygon"
        multipolygon = Mock()
        mock_geos.return_value = polygon
        mock_multi.return_value = multipolygon

        request = self._request_geojson(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"name": "Zona 1"},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[-57, -25], [-57, -24], [-56, -24], [-57, -25]]],
                            },
                        }
                    ],
                }
            )
        )

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_multi.assert_called_once_with(polygon)
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["wkb_geometry"], multipolygon)
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["nombre"], "Zona 1")
        self.assertEqual(kwargs["usu_insercion"], self.user)
        self.assertEqual(kwargs["usu_modificacion"], self.user)

    def test_rechaza_estructura_geojson_no_reconocida(self):
        request = self._request_geojson(json.dumps({"foo": "bar"}))

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])


class EliminarCapaTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.eliminar_capa_view)

    @patch("mapas.views.Capa.objects.get")
    def test_dueno_puede_eliminar_capa(self, mock_get):
        capa = Mock(user_id=8)
        mock_get.return_value = capa
        request = self.factory.post("/eliminar-capa/3/")
        request.user = SimpleNamespace(id=8, is_staff=False, is_authenticated=True)

        response = self.view(request, 3)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        capa.delete.assert_called_once()

    @patch("mapas.views.Capa.objects.get")
    def test_usuario_sin_permiso_no_puede_eliminar_capa(self, mock_get):
        capa = Mock(user_id=8)
        mock_get.return_value = capa
        request = self.factory.post("/eliminar-capa/3/")
        request.user = SimpleNamespace(id=99, is_staff=False, is_authenticated=True)

        response = self.view(request, 3)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(data["success"])
        capa.delete.assert_not_called()


class UsuariosListJsonTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = views.usuarios_list_json

    def test_usuario_no_admin_recibe_403(self):
        request = self.factory.get("/api/usuarios/")
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_staff=False,
            groups=SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(exists=lambda: False)),
        )

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["detail"], "No autorizado")


class MisCapasListJsonTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.mis_capas_list_json)
        self.user = SimpleNamespace(id=12, is_authenticated=True)

    @patch("mapas.views._latest_request_map_for_user")
    @patch("mapas.views.Capa.objects.filter")
    def test_lista_solo_capas_propias(self, mock_filter, mock_latest_requests):
        fecha = SimpleNamespace(isoformat=lambda: "2026-05-11T10:30:00")
        mock_filter.return_value.order_by.return_value = [
            SimpleNamespace(
                ogc_fid=5,
                nombre="Grupo Norte",
                descripcion="Zona de prueba",
                estado="privada",
                fecha_subida=fecha,
            )
        ]
        mock_latest_requests.return_value = {
            5: SimpleNamespace(estado="pendiente", review_comment="Falta revisar metadatos")
        }
        request = self.factory.get("/api/mis-capas/")
        request.user = self.user

        response = self.view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["nombre"], "Grupo Norte")
        self.assertEqual(data["results"][0]["estado"], "pendiente")
        self.assertEqual(data["results"][0]["comentario_revision"], "Falta revisar metadatos")
        mock_filter.assert_called_once_with(user=self.user)


class SolicitarPublicacionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = inspect.unwrap(views.solicitar_publicacion)
        self.user = SimpleNamespace(id=21, is_authenticated=True)

    @patch("mapas.views.SolicitudPublicacion.objects.get_or_create")
    @patch("mapas.views.Capa.objects.get")
    def test_solicita_publicacion_de_capa_propia(self, mock_get, mock_get_or_create):
        capa = Mock()
        mock_get_or_create.return_value = (
            SimpleNamespace(
                estado=SolicitudPublicacion.ESTADO_PENDIENTE,
                capa_nombre="Capa de prueba",
            ),
            True,
        )
        mock_get.return_value = capa
        request = self.factory.post("/api/solicitar-publicacion/8/")
        request.user = self.user

        response = self.view(request, 8)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(capa.estado, "pendiente")
        update_fields = capa.save.call_args.kwargs["update_fields"]
        self.assertCountEqual(update_fields, ["estado", "fec_modificacion", "usu_modificacion"])
        mock_get.assert_called_once_with(pk=8, user=self.user)
        mock_get_or_create.assert_called_once()

    @patch("mapas.views.Capa.objects.get", side_effect=views.Capa.DoesNotExist)
    def test_solicitar_publicacion_devuelve_404_si_no_existe(self, mock_get):
        request = self.factory.post("/api/solicitar-publicacion/8/")
        request.user = self.user

        response = self.view(request, 8)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(data["success"])
        mock_get.assert_called_once_with(pk=8, user=self.user)


class AdminRoleTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.make_admin_view = inspect.unwrap(views.make_admin)
        self.remove_admin_view = inspect.unwrap(views.remove_admin)
        self.request_user = SimpleNamespace(id=1, is_authenticated=True)

    @patch("mapas.views.get_or_create_map_admin_group")
    @patch("mapas.views.User.objects.get")
    def test_make_admin_asigna_grupo_y_staff(self, mock_get_user, mock_get_group):
        group = SimpleNamespace(name="map_admin")
        target = Mock(username="alice")
        mock_get_user.return_value = target
        mock_get_group.return_value = group
        request = self.factory.post("/usuarios/4/make-admin/")
        request.user = self.request_user

        response = self.make_admin_view(request, 4)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        target.groups.add.assert_called_once_with(group)
        self.assertTrue(target.is_staff)
        target.save.assert_called_once()

    @patch("mapas.views.get_or_create_map_admin_group")
    @patch("mapas.views.User.objects.get")
    def test_remove_admin_quita_staff_si_no_quedan_grupos_admin(self, mock_get_user, mock_get_group):
        group = SimpleNamespace(name="map_admin")
        target = Mock(username="bob", is_superuser=False, is_staff=True)
        target.groups.filter.return_value.exists.return_value = False
        mock_get_user.return_value = target
        mock_get_group.return_value = group
        request = self.factory.post("/usuarios/5/remove-admin/")
        request.user = self.request_user

        response = self.remove_admin_view(request, 5)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        target.groups.remove.assert_called_once_with(group)
        self.assertFalse(target.is_staff)
        target.save.assert_called_once()


class SolicitudesPublicacionAdminTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.list_view = inspect.unwrap(views.solicitudes_publicacion_list_json)
        self.resolve_view = inspect.unwrap(views.resolver_solicitud_publicacion)
        self.admin = SimpleNamespace(id=2, is_authenticated=True, is_staff=True)

    @patch("mapas.views.SolicitudPublicacion.objects.filter")
    @patch("mapas.views.SolicitudPublicacion.objects.exclude")
    def test_admin_lista_solicitudes_pendientes_y_resueltas(self, mock_exclude, mock_filter):
        fecha = SimpleNamespace(isoformat=lambda: "2026-05-18T12:00:00")
        mock_filter.return_value.select_related.return_value.order_by.return_value = [
            SimpleNamespace(
                id=11,
                tipo=SolicitudPublicacion.TIPO_GRUPO,
                capa_nombre=None,
                grupo_nombre="PATINO2",
                requester=SimpleNamespace(username="marce"),
                requester_id=3,
                capa_id=None,
                review_comment="",
                created_at=fecha,
            )
        ]
        mock_exclude.return_value.select_related.return_value.order_by.return_value.__getitem__.return_value = [
            SimpleNamespace(
                id=12,
                tipo=SolicitudPublicacion.TIPO_CAPA,
                estado=SolicitudPublicacion.ESTADO_APROBADA,
                capa_nombre="Capa publica",
                grupo_nombre=None,
                requester=SimpleNamespace(username="liz"),
                requester_id=5,
                reviewed_by=SimpleNamespace(username="admin"),
                review_comment="Aprobada correctamente",
                created_at=fecha,
                reviewed_at=fecha,
            )
        ]
        request = self.factory.get("/api/solicitudes-publicacion/")
        request.user = self.admin

        response = self.list_view(request)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["pending"]), 1)
        self.assertEqual(data["pending"][0]["objetivo"], "PATINO2")
        self.assertEqual(len(data["resolved"]), 1)
        self.assertEqual(data["resolved"][0]["reviewed_by"], "admin")

    @patch("mapas.views.timezone.now", return_value="ahora")
    @patch("mapas.views.Muestreo.objects.filter")
    @patch("mapas.views.SolicitudPublicacion.objects.select_related")
    def test_admin_aprueba_solicitud_de_grupo(self, mock_select_related, mock_filter, _mock_now):
        solicitud = Mock(
            tipo=SolicitudPublicacion.TIPO_GRUPO,
            requester=SimpleNamespace(id=3),
            grupo_nombre="PATINO2",
        )
        mock_select_related.return_value.get.return_value = solicitud
        mock_filter.return_value.update.return_value = 7
        request = self.factory.post(
            "/api/solicitudes-publicacion/9/resolver/",
            data=json.dumps({"decision": "aprobar", "comentario": "Publicacion aprobada."}),
            content_type="application/json",
        )
        request.user = self.admin

        response = self.resolve_view(request, 9)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        mock_filter.assert_called_once_with(user=solicitud.requester, grupo="PATINO2")
        update_kwargs = mock_filter.return_value.update.call_args.kwargs
        self.assertTrue(update_kwargs["publico"])
        self.assertEqual(update_kwargs["usu_modificacion_id"], self.admin.id)
        self.assertEqual(update_kwargs["fec_modificacion"], "ahora")
        self.assertEqual(solicitud.estado, SolicitudPublicacion.ESTADO_APROBADA)
        self.assertEqual(solicitud.review_comment, "Publicacion aprobada.")
        solicitud.save.assert_called_once()


class AuthAndPreferencesIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="marce",
            password="ClaveSegura123",
        )

    def test_login_view_autentica_usuario_real(self):
        response = self.client.post(
            "/login/",
            data={"username": "marce", "password": "ClaveSegura123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/mapa-muestreo/")

    def test_login_view_modal_devuelve_json_en_ajax(self):
        response = self.client.post(
            "/login/",
            data={
                "username": "marce",
                "password": "ClaveSegura123",
                "modal_login": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True, "redirect_url": "/mapa-muestreo/"})

    def test_register_modal_crea_usuario_y_autentica(self):
        response = self.client.post(
            "/register/",
            data={
                "username": "nuevo_modal",
                "password": "ClaveModal123",
                "modal_register": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(data["redirect_url"], "/mapa-muestreo/")
        self.assertTrue(User.objects.filter(username="nuevo_modal").exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(username="nuevo_modal").id)

    def test_register_modal_rechaza_usuario_duplicado(self):
        response = self.client.post(
            "/register/",
            data={
                "username": "marce",
                "password": "ClaveModal123",
                "modal_register": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data["success"])
        self.assertIn("username", data["field_errors"])

    def test_logout_redirige_al_mapa(self):
        self.client.force_login(self.user)
        response = self.client.get("/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/mapa-muestreo/")

    def test_register_crea_usuario_y_redirige_al_login(self):
        response = self.client.post(
            "/register/",
            data={
                "username": "nuevo_usuario",
                "password1": "OtraClaveSegura123",
                "password2": "OtraClaveSegura123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")
        self.assertTrue(User.objects.filter(username="nuevo_usuario").exists())

    def test_guardar_centro_mapa_crea_preferencia_real(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/guardar-centro/",
            data=json.dumps({"lat": -25.31, "lng": -57.58}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True})

        pref = PreferenciasMapa.objects.get(user=self.user)
        self.assertAlmostEqual(pref.centro_mapa.y, -25.31, places=6)
        self.assertAlmostEqual(pref.centro_mapa.x, -57.58, places=6)

    def test_guardar_centro_mapa_rechaza_payload_incompleto(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/guardar-centro/",
            data=json.dumps({"lat": -25.31}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data["success"])

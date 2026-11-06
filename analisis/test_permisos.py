"""Permisos por rol (lista blanca) y validación de parámetros."""
import os

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from analisis.permisos import puede_cargar_datos
from analisis.utilidades_pruebas import PruebaConMedia, crear_usuario


class _UsuarioFalso:
    def __init__(self, rol, is_staff=False, is_active=True):
        self.rol, self.is_staff, self.is_active = rol, is_staff, is_active
        self.is_authenticated = True


class ReglaDePermisoTests(SimpleTestCase):

    def test_roles_autorizados(self):
        self.assertTrue(puede_cargar_datos(_UsuarioFalso("docente")))
        self.assertTrue(puede_cargar_datos(_UsuarioFalso("admin")))

    def test_staff_aunque_su_rol_sea_estudiante(self):
        # createsuperuser deja rol='estudiante' (valor por defecto) con is_staff=True
        self.assertTrue(puede_cargar_datos(_UsuarioFalso("estudiante", is_staff=True)))

    def test_roles_sin_permiso_o_desconocidos(self):
        for rol in ("estudiante", "tecnico", "", None, "DOCENTE"):
            with self.subTest(rol=rol):
                self.assertFalse(puede_cargar_datos(_UsuarioFalso(rol)))

    def test_cuenta_inactiva_o_anonima(self):
        self.assertFalse(puede_cargar_datos(_UsuarioFalso("docente", is_active=False)))
        self.assertFalse(puede_cargar_datos(AnonymousUser()))
        self.assertFalse(puede_cargar_datos(None))


class PermisosEnVistasTests(PruebaConMedia):

    def setUp(self):
        self.estudiante = crear_usuario("estudiante", "estudiante")
        self.docente = crear_usuario("docente", "docente")
        self.admin = crear_usuario("admin", "admin", is_staff=True, is_superuser=True)
        self.superusuario_inicial = crear_usuario("root", "estudiante", is_staff=True, is_superuser=True)
        self.rol_desconocido = crear_usuario("tecnico", "tecnico")

    def _get(self, usuario, url):
        self.client.force_login(usuario)
        return self.client.get(url)

    def test_subir_datos(self):
        url = reverse("analisis:subir_datos")
        for usuario in (self.docente, self.admin, self.superusuario_inicial):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self._get(usuario, url).status_code, 200)
        for usuario in (self.estudiante, self.rol_desconocido):
            with self.subTest(usuario=usuario.username):
                resp = self._get(usuario, url)
                self.assertRedirects(resp, reverse("analisis:dashboard"), fetch_redirect_response=False)

    def test_bioquimica_carga(self):
        for nombre in ("bioquimica:subir_pdf", "bioquimica:ingreso_manual"):
            url = reverse(nombre)
            with self.subTest(vista=nombre):
                self.assertEqual(self._get(self.docente, url).status_code, 200)
                for usuario in (self.estudiante, self.rol_desconocido):
                    resp = self._get(usuario, url)
                    self.assertRedirects(resp, reverse("bioquimica:lista"), fetch_redirect_response=False)

    def test_media_restringida(self):
        from django.conf import settings
        ruta = os.path.join(settings.MEDIA_ROOT, "archivos_moleculares", "16S")
        os.makedirs(ruta, exist_ok=True)
        with open(os.path.join(ruta, "M1_datos.csv"), "wb") as f:
            f.write(b"genus\nBacillus\n")
        url = "/media/archivos_moleculares/16S/M1_datos.csv"

        resp = self._get(self.docente, url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Disposition"], "attachment")
        self.assertEqual(resp.getvalue(), b"genus\nBacillus\n")
        for usuario in (self.estudiante, self.rol_desconocido):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self._get(usuario, url).status_code, 403)

        self.client.logout()
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("analisis:login"), resp["Location"])

    def test_menu_de_carga_segun_permiso(self):
        url_pdf = reverse("bioquimica:subir_pdf")
        self.assertIn(url_pdf, self._get(self.docente, reverse("bioquimica:lista")).content.decode())
        self.assertNotIn(url_pdf, self._get(self.estudiante, reverse("bioquimica:lista")).content.decode())


@override_settings(SECURE_SSL_REDIRECT=False)
class ParametrosInvalidosTests(PruebaConMedia):

    def setUp(self):
        self.client.force_login(crear_usuario("docente", "docente"))

    def test_cargar_variedades_con_id_no_numerico(self):
        resp = self.client.get(reverse("analisis:cargar_variedades"), {"cultivo_id": "abc"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"variedades": []})

    def test_cargar_variedades_valido(self):
        resp = self.client.get(reverse("analisis:cargar_variedades"), {"cultivo_id": self.cultivo.pk})
        self.assertEqual(resp.json()["variedades"], [{"id": self.variedad.pk, "nombre": "CCN-51"}])

    def test_analisis_avanzado_normaliza_tipo_y_nivel(self):
        resp = self.client.get(reverse("analisis:analisis_avanzado"),
                               {"tipo": "<b>X</b>", "nivel": "drop", "top_n": "abc"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["tipo_actual"], "16S")
        self.assertEqual(resp.context["nivel_actual"], "genus")
        self.assertEqual(resp.context["top_n_actual"], 10)

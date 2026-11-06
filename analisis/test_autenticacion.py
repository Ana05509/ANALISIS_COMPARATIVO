"""Bloqueo de login atómico entre procesos y prevención de enumeración de cuentas."""
import threading
from unittest import mock

from django.core import mail
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from analisis import seguridad
from analisis.models import BloqueoLogin
from analisis.utilidades_pruebas import crear_usuario


class BloqueoConcurrenteTests(TransactionTestCase):
    """Dos fallos simultáneos (conexiones distintas) no deben perder una actualización."""

    def _fallos_simultaneos(self, correo, n):
        barrera = threading.Barrier(n)
        resultados, errores = [], []

        def intento():
            try:
                barrera.wait(timeout=10)
                resultados.append(seguridad.registrar_fallo(correo))
            except Exception as exc:  # pragma: no cover - solo para informar en la prueba
                errores.append(exc)
            finally:
                connection.close()  # cada hilo usa su propia conexión

        hilos = [threading.Thread(target=intento) for _ in range(n)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(errores, [])
        return sorted(resultados)

    def test_tercer_fallo_simultaneo_bloquea(self):
        correo = "carrera@utc.edu.ec"
        seguridad.registrar_fallo(correo)                       # 1.º fallo
        self.assertEqual(self._fallos_simultaneos(correo, 2), [0, 1])  # 2.º y 3.º a la vez
        self.assertEqual(seguridad.minutos_bloqueo_restantes(correo), seguridad.MINUTOS_BLOQUEO)

    def test_primer_fallo_simultaneo_crea_una_sola_fila(self):
        correo = "nuevo@utc.edu.ec"
        self.assertEqual(self._fallos_simultaneos(correo, 2), [1, 2])
        self.assertEqual(BloqueoLogin.objects.count(), 1)


class VentanaDeslizanteTests(TestCase):

    def test_solo_cuentan_los_fallos_de_los_ultimos_15_minutos(self):
        correo = "ventana@utc.edu.ec"
        t0 = 1_800_000_000.0
        with mock.patch("analisis.seguridad.time.time", return_value=t0):
            seguridad.registrar_fallo(correo)
        with mock.patch("analisis.seguridad.time.time", return_value=t0 + 14 * 60):
            self.assertEqual(seguridad.registrar_fallo(correo), 1)
        # El primer fallo ya salió de la ventana: quedan 2 fallos, no 3
        with mock.patch("analisis.seguridad.time.time", return_value=t0 + 16 * 60):
            self.assertEqual(seguridad.registrar_fallo(correo), 1)
            self.assertEqual(seguridad.minutos_bloqueo_restantes(correo), 0)

    def test_no_guarda_el_correo_en_claro(self):
        seguridad.registrar_fallo("privado@utc.edu.ec")
        fila = BloqueoLogin.objects.get()
        self.assertNotIn("privado", fila.clave)
        self.assertEqual(len(fila.clave), 64)


class LoginBloqueadoTests(TestCase):

    def setUp(self):
        crear_usuario("ana", "docente")

    def test_bloqueo_rechaza_la_contrasena_correcta(self):
        url = reverse("analisis:login")
        for _ in range(seguridad.INTENTOS_MAXIMOS):
            self.client.post(url, {"username": "ana@utc.edu.ec", "password": "incorrecta"})
        resp = self.client.post(url, {"username": "ana@utc.edu.ec", "password": "ClaveSegura.2026"})
        self.assertEqual(resp.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)


class EnumeracionDeCuentasTests(TestCase):

    def setUp(self):
        crear_usuario("ana", "docente")

    def _reset(self, email):
        with mock.patch("analisis.adapter._domain_can_receive_email", return_value=True):
            return self.client.post(reverse("account_reset_password"), {"email": email})

    def test_recuperar_contrasena_responde_igual_exista_o_no(self):
        existe = self._reset("ana@utc.edu.ec")
        no_existe = self._reset("nadie@utc.edu.ec")
        self.assertEqual(existe.status_code, 302)
        self.assertEqual(no_existe.status_code, 302)
        self.assertEqual(existe["Location"], no_existe["Location"])

    def test_no_envia_correos_a_direcciones_no_registradas(self):
        self._reset("nadie@utc.edu.ec")
        self.assertEqual(len(mail.outbox), 0)
        self._reset("ana@utc.edu.ec")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@utc.edu.ec"])

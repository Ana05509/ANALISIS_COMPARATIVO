from django.db import models
from django.db.models import F
from django.conf import settings


class EnsayoMicrobiologico(models.Model):
    TIPO_ENSAYO = [
        ('recuento', 'Recuento de Microorganismos (UFC/g)'),
        ('aislamiento', 'Aislamiento e Identificación'),
    ]

    codigo = models.CharField(max_length=50, unique=True, verbose_name="Código del Ensayo",
                              help_text="Ej: MAg-225-2023")
    tipo = models.CharField(max_length=20, choices=TIPO_ENSAYO, db_index=True,
                            verbose_name="Tipo de Ensayo")
    nombre_muestra = models.CharField(max_length=200, verbose_name="Nombre de la Muestra",
                                      help_text="Ej: Suelo #1")
    etiqueta = models.TextField(blank=True, verbose_name="Etiqueta de la Muestra",
                                help_text="Información de la etiqueta física: fecha, lote, sección, etc.")
    # null=True: algunos informes de origen (ej. formato CIPAL) no traen
    # fecha en ningún lado del documento — antes se rellenaba con la fecha
    # de HOY (de importación), lo que hacía ver una muestra de 2011 como si
    # fuera de la fecha en que se subió el PDF. Ahora se deja sin fecha y
    # se anota en `observaciones` (ver _guardar_ensayo en views.py).
    fecha_recepcion = models.DateField(null=True, blank=True, verbose_name="Fecha de Recepción")
    fecha_ejecucion = models.DateField(null=True, blank=True, verbose_name="Fecha de Ejecución")
    fecha_reporte = models.DateField(null=True, blank=True, verbose_name="Fecha del Reporte")
    # La marca real de "esto vino del laboratorio CIPAL" — la pone
    # _guardar_ensayo en views.py solo cuando pdf_parser.parsear_pdf()
    # detectó el formato CIPAL (ver services/pdf_parser.py). No basta con
    # mirar si el ensayo tiene filas RecuentoUFC tipo "Otro/Mixto": ese
    # mecanismo también lo usa el ingreso manual para CUALQUIER laboratorio
    # que reporte varias mediciones por fila, no solo CIPAL — sin este
    # campo, un ensayo manual de otro origen se etiquetaría como CIPAL por
    # error.
    es_cipal = models.BooleanField(default=False, verbose_name="Formato CIPAL",
                                   help_text="Se marca automáticamente al importar un PDF de CIPAL.")
    temp_ambiental = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                         verbose_name="Temperatura Ambiental (°C)")
    humedad_ambiental = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                             verbose_name="Humedad Ambiental (%)")
    observaciones = models.TextField(blank=True, verbose_name="Observaciones")
    archivo_pdf = models.FileField(
        upload_to='bioquimica_pdfs/', null=True, blank=True,
        verbose_name="PDF del Reporte Original"
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ensayos_clasicos',
        verbose_name="Registrado por"
    )
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Ingreso al Sistema")

    class Meta:
        verbose_name = "Ensayo Microbiológico"
        verbose_name_plural = "Ensayos Microbiológicos"
        # fecha_reporte puede ser None (informes CIPAL sin fecha, ver arriba).
        # En PostgreSQL, ORDER BY ... DESC pone los NULL primero por defecto,
        # así que sin nulls_last un ensayo sin fecha aparecería antes que
        # todos los ensayos con fecha reciente. nulls_last=True lo manda al
        # final; fecha_registro como criterio secundario ordena esos casos
        # sin fecha por orden de ingreso al sistema (más reciente primero).
        ordering = [F('fecha_reporte').desc(nulls_last=True), '-fecha_registro']

    def __str__(self):
        return f"{self.codigo} — {self.nombre_muestra}"

    def total_organismos(self):
        if self.tipo == 'recuento':
            return self.recuentos.count()
        return self.aislados.count()


class RecuentoUFC(models.Model):
    TIPO_ORGANISMO = [
        ('hongo', 'Hongo'),
        ('bacteria', 'Bacteria'),
        # Para filas que no son un microorganismo puntual sino una muestra/
        # tratamiento con varias mediciones a la vez (ej. un laboratorio que
        # reporta Bacterias + Hongos + Actinomicetes + grupos funcionales en
        # una sola fila) — esas mediciones van como ParametroRecuento en vez
        # de forzarlas a "bacteria" o "hongo".
        ('otro', 'Otro / Mixto'),
    ]

    ensayo = models.ForeignKey(EnsayoMicrobiologico, on_delete=models.CASCADE,
                               related_name='recuentos', verbose_name="Ensayo")
    tipo_organismo = models.CharField(max_length=10, choices=TIPO_ORGANISMO,
                                      verbose_name="Tipo de Organismo")
    nombre = models.CharField(max_length=200, verbose_name="Nombre del Microorganismo",
                              help_text="Ej: Bacterias totales, Bacillus spp.")
    coeficiente = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                      verbose_name="Coeficiente",
                                      help_text="El número antes de ×10^n. Ej: 3 en 3×10⁶")
    exponente = models.IntegerField(null=True, blank=True, verbose_name="Exponente (n)",
                                    help_text="El exponente de base 10. Ej: 6 en 3×10⁶")
    menor_que_limite = models.BooleanField(default=False, verbose_name="Menor que límite de detección",
                                           help_text="Marcar si el resultado es <1 UFC/g")
    orden = models.PositiveSmallIntegerField(default=0, verbose_name="Orden de visualización")

    class Meta:
        verbose_name = "Recuento UFC/g"
        verbose_name_plural = "Recuentos UFC/g"
        ordering = ['orden', 'tipo_organismo', 'nombre']

    def __str__(self):
        return f"{self.nombre}: {self.valor_display}"

    @property
    def valor_display(self):
        if self.menor_que_limite:
            return "<1 UFC/g"
        if self.coeficiente is None:
            return "—"
        exp = self.exponente or 0
        if exp > 0:
            return f"{self.coeficiente} × 10⁰{exp} UFC/g" if exp < 10 else f"{self.coeficiente} × 10^{exp} UFC/g"
        return f"{self.coeficiente} UFC/g"

    @property
    def valor_numerico(self):
        """Valor numérico para graficar en escala logarítmica."""
        if self.menor_que_limite:
            return 0.5
        if self.coeficiente is None:
            return 0
        return float(self.coeficiente) * (10 ** (self.exponente or 0))

    def tiene_parametros(self):
        return self.parametros.exists()


class ParametroRecuento(models.Model):
    """Mediciones adicionales de un recuento, con nombre y valor libres —
    mismo rol que PruebaBioquimica para Aislamiento, pero del lado de
    Recuento: para laboratorios que reportan otra unidad, otra escala, o
    varias mediciones a la vez por fila (ver TIPO_ORGANISMO='otro' arriba)."""
    recuento = models.ForeignKey(RecuentoUFC, on_delete=models.CASCADE,
                                 related_name='parametros', verbose_name="Recuento")
    numero = models.PositiveSmallIntegerField(default=0, verbose_name="N°")
    nombre = models.CharField(max_length=200, verbose_name="Parámetro",
                              help_text="Ej: Coliformes totales, pH, Humedad, NMP/g…")
    valor = models.CharField(max_length=200, verbose_name="Valor",
                             help_text="Ej: 5.2 log UFC/g, <10 NMP/g, 6.8…")

    class Meta:
        ordering = ['numero']
        verbose_name = "Parámetro Adicional de Recuento"
        verbose_name_plural = "Parámetros Adicionales de Recuento"

    def __str__(self):
        return f"{self.numero}. {self.nombre}: {self.valor}"


class MicroorganismoAislado(models.Model):
    TIPO = [
        ('hongo', 'Hongo'),
        ('bacteria', 'Bacteria'),
    ]

    ensayo = models.ForeignKey(EnsayoMicrobiologico, on_delete=models.CASCADE,
                               related_name='aislados', verbose_name="Ensayo")
    tipo = models.CharField(max_length=10, choices=TIPO, verbose_name="Tipo de Organismo")
    nombre_cientifico = models.CharField(max_length=200, verbose_name="Nombre Científico",
                                         help_text="Ej: Pseudomonas spp.")
    dominio = models.CharField(max_length=100, blank=True, verbose_name="Dominio")
    filo = models.CharField(max_length=100, blank=True, verbose_name="Filo")
    clase = models.CharField(max_length=100, blank=True, verbose_name="Clase")
    orden_taxonomico = models.CharField(max_length=100, blank=True, verbose_name="Orden")
    familia = models.CharField(max_length=100, blank=True, verbose_name="Familia")
    genero = models.CharField(max_length=100, blank=True, verbose_name="Género")
    especie = models.CharField(max_length=100, blank=True, verbose_name="Especie")

    class Meta:
        verbose_name = "Microorganismo Aislado"
        verbose_name_plural = "Microorganismos Aislados"
        ordering = ['tipo', 'nombre_cientifico']

    def __str__(self):
        return f"{self.nombre_cientifico} ({self.get_tipo_display()})"

    def tiene_taxonomia(self):
        return any([self.dominio, self.filo, self.clase, self.orden_taxonomico,
                    self.familia, self.genero, self.especie])

    def tiene_pruebas(self):
        return self.pruebas.exists()


class PruebaBioquimica(models.Model):
    microorganismo = models.ForeignKey(MicroorganismoAislado, on_delete=models.CASCADE,
                                       related_name='pruebas', verbose_name="Microorganismo")
    numero = models.PositiveSmallIntegerField(verbose_name="N°")
    nombre_prueba = models.CharField(max_length=200, verbose_name="Prueba")
    resultado = models.CharField(max_length=200, verbose_name="Resultado",
                                 help_text="Ej: +, -, C, NC, Gram positivos, Bacilos...")

    class Meta:
        verbose_name = "Prueba Bioquímica"
        verbose_name_plural = "Pruebas Bioquímicas"
        ordering = ['numero']

    def __str__(self):
        return f"{self.numero}. {self.nombre_prueba}: {self.resultado}"

    @property
    def resultado_clase(self):
        """CSS class para colorear el resultado en la tabla."""
        r = self.resultado.strip().lower()
        if r in ('+', 'c', 'crecimiento'):
            return 'positivo'
        if r in ('-', 'nc', 'no hay crecimiento'):
            return 'negativo'
        return 'neutro'

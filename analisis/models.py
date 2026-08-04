from django.db import models
from django.contrib.auth.models import AbstractUser
from simple_history.models import HistoricalRecords

# Modelos de Catálogo Agronómico

class Cultivo(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Cultivo")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    imagen = models.ImageField(
        upload_to='cultivos/',
        blank=True, null=True,
        verbose_name="Imagen / Fotografía",
        help_text="Sube un archivo JPG, PNG o WEBP desde tu computadora."
    )
    imagen_url = models.URLField(
        max_length=500,
        blank=True, null=True,
        verbose_name="URL de imagen externa",
        help_text="Pega el enlace directo a una imagen en línea (https://...). Se usa si no hay archivo subido."
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Cultivo"
        verbose_name_plural = "Cultivos"

    def __str__(self):
        return self.nombre


class VariedadClon(models.Model):
    cultivo = models.ForeignKey(
        Cultivo, on_delete=models.CASCADE,
        related_name="variedades", verbose_name="Cultivo Base"
    )
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Variedad/Clon")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cultivo', 'nombre'],
                name='unique_cultivo_variedad'
            )
        ]
        verbose_name = "Variedad o Clon"
        verbose_name_plural = "Variedades o Clones"

    def __str__(self):
        return f"{self.cultivo.nombre} - {self.nombre}"


# ---------------------------------
# Muestras de Suelo y Datos Asociados
# ---------------------------------

class MuestraSuelo(models.Model):
    codigo = models.CharField(max_length=100, unique=True, verbose_name="Código de la Muestra")
    cultivo = models.ForeignKey(
        Cultivo, on_delete=models.PROTECT,
        related_name="muestras", verbose_name="Cultivo"
    )
    variedad_clon = models.ForeignKey(
        VariedadClon, on_delete=models.PROTECT,
        related_name="muestras", verbose_name="Variedad o Clon"
    )
    tipo_muestra = models.CharField(max_length=100, default="Suelo", verbose_name="Tipo de Muestra")
    observaciones = models.TextField(blank=True, verbose_name="Observaciones de Campo")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Ingreso")
    localidad = models.CharField(max_length=100, db_index=True, verbose_name="Localidad")
    finca_lote = models.CharField(max_length=150, verbose_name="Finca / Lote")
    altitud = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Altitud (msnm)")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Muestra de Suelo"
        verbose_name_plural = "Muestras de Suelo"

    def __str__(self):
        return f"Muestra: {self.codigo}"


# Ruta dinámica para archivos moleculares
def ruta_archivo_molecular(instance, filename):
    # Ejemplo: archivos_moleculares/16S/M001_muestra.csv
    return f"archivos_moleculares/{instance.tipo_analisis}/{instance.muestra.codigo}_{filename}"


class ArchivoMolecular(models.Model):
    TIPOS_ANALISIS = [
        ("16S", "16S (Bacterias)"),
        ("ITS", "ITS (Hongos)"),
    ]

    muestra = models.ForeignKey(
        MuestraSuelo, on_delete=models.CASCADE,
        related_name="archivos_moleculares", verbose_name="Muestra de Suelo"
    )
    tipo_analisis = models.CharField(max_length=10, choices=TIPOS_ANALISIS, db_index=True, verbose_name="Tipo de Marcador")
    archivo = models.FileField(upload_to=ruta_archivo_molecular, verbose_name="Archivo de Secuenciación (CSV/Excel)")
    fecha_carga = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Subida")

    class Meta:
        verbose_name = "Archivo Molecular"
        verbose_name_plural = "Archivos Moleculares"

    def __str__(self):
        return f"{self.tipo_analisis} - Muestra: {self.muestra.codigo}"


class ResultadoTaxonomico(models.Model):
    archivo = models.ForeignKey(
        ArchivoMolecular, on_delete=models.CASCADE,
        related_name="resultados_taxonomicos"
    )

    kingdom = models.CharField(max_length=255, blank=True, db_index=True)
    phylum = models.CharField(max_length=255, blank=True, db_index=True)
    tax_class = models.CharField(max_length=255, blank=True)
    order = models.CharField(max_length=255, blank=True)
    family = models.CharField(max_length=255, blank=True, db_index=True)
    genus = models.CharField(max_length=255, blank=True, db_index=True)
    species = models.CharField(max_length=255, blank=True, db_index=True)

    num_hits = models.IntegerField(default=0, verbose_name="Conteo de Abundancia")
    porcentaje_hits = models.FloatField(default=0.0, verbose_name="Abundancia Relativa (%)")

    class Meta:
        verbose_name = "Resultado Taxonómico"
        verbose_name_plural = "Resultados Taxonómicos"
        indexes = [
            models.Index(fields=['archivo', 'num_hits']),
            models.Index(fields=['genus', 'num_hits']),
        ]

    def __str__(self):
        genus_display = self.genus if self.genus else "Unclassified"
        species_display = self.species if self.species else "sp."
        return f"{genus_display} {species_display} ({self.porcentaje_hits}%)"


class CatalogoMicroorganismo(models.Model):
    CLASIFICACIONES = [
        ("benefico", "Benéfico"),
        ("fitopatogeno", "Potencial fitopatógeno"),
        ("neutral", "Neutral"),
        ("sin_clasificar", "Sin clasificación"),
    ]

    MARCADOR_CHOICES = [
        ("16S", "Bacteria"),
        ("ITS", "Hongo"),
    ]

    NIVEL_CHOICES = [
        ("genus",   "Género"),
        ("species", "Especie"),
        ("family",  "Familia"),
        ("order",   "Orden"),
        ("class",   "Clase"),
        ("phylum",  "Filo"),
    ]

    nombre = models.CharField(max_length=255, db_index=True, verbose_name="Nombre Científico",
                              help_text="Ej: Bacillus")
    nivel = models.CharField(max_length=50, db_index=True, choices=NIVEL_CHOICES,
                             verbose_name="Nivel Taxonómico",
                             help_text="Nivel taxonómico canónico del organismo")
    clasificacion = models.CharField(max_length=30, choices=CLASIFICACIONES, db_index=True,
                                     verbose_name="Rol Funcional")
    descripcion = models.TextField(blank=True, verbose_name="Descripción Agronómica")
    referencia = models.TextField(blank=True, verbose_name="Referencia Literaria",
                                  help_text="Literatura científica que respalda la clasificación")

    # Nuevo campo solo con 16S e ITS
    marcador = models.CharField(
        max_length=10,
        choices=MARCADOR_CHOICES,
        default="16S",          # valor por defecto
        verbose_name="Marcador Molecular",
        help_text="Región genética usada para identificación (16S o ITS)"
    )
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['nombre', 'nivel'], name='unique_nombre_nivel')
        ]
        verbose_name = "Microorganismo de Catálogo"
        verbose_name_plural = "Catálogo de Microorganismos"

    def __str__(self):
        return f"{self.nombre} [{self.get_clasificacion_display()}] - {self.get_marcador_display()}"

# ---------------------------------
# Modelo de Usuario Personalizado
# ---------------------------------

class Usuario(AbstractUser):
    ROLES = (
        ('admin', 'Administrador'),
        ('docente', 'Docente / Investigador'),
        ('estudiante', 'Estudiante'),
    )

    rol = models.CharField(
        max_length=20,
        choices=ROLES,
        default='estudiante',
        verbose_name="Rol en la Plataforma"
    )
    avatar = models.ImageField(
        upload_to='avatars/',
        blank=True,
        null=True,
        verbose_name="Foto de perfil"
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def save(self, *args, **kwargs):
        if self.first_name:
            self.first_name = self.first_name.strip().title()
        if self.last_name:
            self.last_name = self.last_name.strip().title()
        super().save(*args, **kwargs)

    def __str__(self):
        rol_display = dict(self.ROLES).get(self.rol, self.rol)
        return f"{self.username} ({rol_display})"


# ---------------------------------
# Auditoría — Eventos de Acceso
# ---------------------------------

def _parsear_user_agent(ua):
    """
    Identifica navegador y sistema operativo a partir del User-Agent.
    Parser propio y liviano (sin dependencia externa) para los casos más
    comunes — no pretende cubrir cada variante existente, solo lo suficiente
    para que la bitácora de auditoría sea legible para una persona.
    """
    if not ua:
        return "Desconocido", "Desconocido"

    ua_l = ua.lower()

    if "edg/" in ua_l:
        navegador = "Edge"
    elif "opr/" in ua_l or "opera" in ua_l:
        navegador = "Opera"
    elif "firefox/" in ua_l:
        navegador = "Firefox"
    elif "chrome/" in ua_l:
        navegador = "Chrome"
    elif "safari/" in ua_l:
        navegador = "Safari"
    else:
        navegador = "Otro"

    if "windows nt" in ua_l:
        so = "Windows"
    elif "android" in ua_l:
        so = "Android"
    elif "iphone" in ua_l or "ipad" in ua_l:
        so = "iOS"
    elif "mac os x" in ua_l:
        so = "macOS"
    elif "linux" in ua_l:
        so = "Linux"
    else:
        so = "Otro"

    return navegador, so


class EventoAcceso(models.Model):
    """
    Bitácora de autenticación: quién entró, quién intentó entrar y falló,
    y quién salió — con IP y user-agent. Se completa sola vía señales de
    Django/allauth (ver Usuario.apps.AnalisisConfig.ready()), nunca a mano.

    Es intencionalmente de solo lectura desde el admin (ver EventoAccesoAdmin):
    un registro de auditoría que se puede editar o borrar deja de servir como
    evidencia — si alguna vez hace falta purgar historial viejo, debe ser por
    un comando de gestión con su propio registro, no por el botón "eliminar"
    de cualquier admin con sesión abierta.
    """
    TIPOS = (
        ("login_ok", "Inicio de sesión exitoso"),
        ("login_fallido", "Intento de inicio de sesión fallido"),
        ("logout", "Cierre de sesión"),
    )

    tipo = models.CharField(max_length=20, choices=TIPOS, db_index=True, verbose_name="Tipo de Evento")
    usuario = models.ForeignKey(
        Usuario, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="eventos_acceso", verbose_name="Usuario",
        help_text="Vacío en login_fallido cuando el usuario/correo ingresado no existe."
    )
    username_intentado = models.CharField(
        max_length=150, blank=True, verbose_name="Usuario/correo ingresado",
        help_text="Tal como se escribió en el formulario; útil para login_fallido."
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True, verbose_name="Dirección IP")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="Navegador / Dispositivo")
    fecha = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Fecha y Hora")

    class Meta:
        verbose_name = "Evento de Acceso"
        verbose_name_plural = "Eventos de Acceso"
        ordering = ["-fecha"]

    def __str__(self):
        quien = self.usuario.username if self.usuario is not None else (self.username_intentado or "desconocido")
        return f"{self.get_tipo_display()} — {quien} — {self.fecha:%Y-%m-%d %H:%M}"

    @property
    def navegador(self):
        return _parsear_user_agent(self.user_agent)[0]

    @property
    def sistema_operativo(self):
        return _parsear_user_agent(self.user_agent)[1]

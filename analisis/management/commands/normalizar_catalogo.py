"""
Normaliza el campo `nivel` de CatalogoMicroorganismo de español a inglés,
que es el formato que usa el resto del sistema (NIVELES_VALIDOS).

Uso:
    python manage.py normalizar_catalogo            # dry-run (muestra qué cambiaría)
    python manage.py normalizar_catalogo --aplicar  # aplica los cambios
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from analisis.models import CatalogoMicroorganismo

MAPA_ES_EN = {
    # español → inglés (insensible a mayúsculas)
    "género":   "genus",
    "genero":   "genus",
    "especie":  "species",
    "familia":  "family",
    "orden":    "order",
    "clase":    "class",
    "filo":     "phylum",
    "reino":    "kingdom",
    # por si ya vienen en inglés con variantes
    "genus":    "genus",
    "species":  "species",
    "family":   "family",
    "order":    "order",
    "phylum":   "phylum",
    "kingdom":  "kingdom",
}


class Command(BaseCommand):
    help = "Normaliza el campo nivel del catálogo de español a inglés"

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar",
            action="store_true",
            default=False,
            help="Aplica los cambios (sin este flag solo muestra lo que haría)",
        )

    def handle(self, *args, **options):
        aplicar = options["aplicar"]
        S = self.style.SUCCESS
        W = self.style.WARNING
        E = self.style.ERROR

        self.stdout.write("\n=== NORMALIZACION DE NIVELES EN CATALOGO ===\n")

        # Muestra los valores actuales
        from django.db.models import Count
        niveles = list(
            CatalogoMicroorganismo.objects.values("nivel")
            .annotate(n=Count("id"))
            .order_by("-n")
        )

        self.stdout.write("Valores actuales en el campo nivel:")
        for row in niveles:
            nivel_orig  = row["nivel"]
            nivel_norm  = MAPA_ES_EN.get(nivel_orig.lower().strip())
            estado      = S("→ " + nivel_norm) if nivel_norm else E("SIN MAPEO")
            self.stdout.write(f"  {nivel_orig!r:20s}  ({row['n']:4d} entradas)   {estado}")

        if not aplicar:
            self.stdout.write(W("\nModo DRY-RUN. Ejecuta con --aplicar para hacer los cambios."))
            return

        # Aplica cambios
        total_actualizados = 0
        with transaction.atomic():
            for row in niveles:
                nivel_orig = row["nivel"]
                nivel_norm = MAPA_ES_EN.get(nivel_orig.lower().strip())
                if nivel_norm and nivel_norm != nivel_orig:
                    n = CatalogoMicroorganismo.objects.filter(nivel=nivel_orig).update(nivel=nivel_norm)
                    total_actualizados += n
                    self.stdout.write(S(f"  Actualizado: {nivel_orig!r} -> {nivel_norm!r}  ({n} entradas)"))
                elif not nivel_norm:
                    self.stdout.write(E(f"  SIN MAPEO: {nivel_orig!r} ({row['n']} entradas) — dejado sin cambios"))

        self.stdout.write(S(f"\nListo. {total_actualizados} entradas actualizadas.\n"))

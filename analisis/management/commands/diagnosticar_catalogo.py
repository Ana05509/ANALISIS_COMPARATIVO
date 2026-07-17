"""
python manage.py diagnosticar_catalogo
python manage.py diagnosticar_catalogo --tipo ITS --nivel genus
python manage.py diagnosticar_catalogo --tipo 16S --nivel species --top 20
"""
from django.core.management.base import BaseCommand
from django.db.models import F, Sum

from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo
from analisis.constants import MAPA_NIVELES


class Command(BaseCommand):
    help = "Diagnóstico de coincidencias entre resultados taxonómicos y catálogo"

    def add_arguments(self, parser):
        parser.add_argument("--tipo",  default="16S", choices=["16S","ITS"])
        parser.add_argument("--nivel", default="genus")
        parser.add_argument("--top",   type=int, default=30)

    def handle(self, *args, **options):
        tipo  = options["tipo"]
        nivel = options["nivel"]
        top   = options["top"]
        campo = MAPA_NIVELES.get(nivel, "genus")

        W = self.style.WARNING
        S = self.style.SUCCESS
        E = self.style.ERROR

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"  DIAGNÓSTICO  marcador={tipo}  nivel={nivel}")
        self.stdout.write(f"{'='*60}\n")

        # ── 1. Estado del catálogo ──────────────────────────────────────
        total_cat = CatalogoMicroorganismo.objects.count()
        cat_tipo  = CatalogoMicroorganismo.objects.filter(marcador=tipo).count()
        cat_nivel = CatalogoMicroorganismo.objects.filter(marcador=tipo, nivel__iexact=nivel).count()

        self.stdout.write(S("CATÁLOGO"))
        self.stdout.write(f"  Total entradas en catálogo:              {total_cat}")
        self.stdout.write(f"  Entradas para marcador '{tipo}':         {cat_tipo}")
        self.stdout.write(f"  Entradas marcador='{tipo}' nivel='{nivel}': {cat_nivel}")

        if cat_tipo == 0:
            self.stdout.write(E(f"\n  ⚠  El catálogo NO tiene entradas para marcador='{tipo}'."))
            self.stdout.write(E("     Añade microorganismos al catálogo desde el Admin o fixtures.\n"))
            return

        if cat_nivel == 0:
            self.stdout.write(W(f"\n  ⚠  Hay {cat_tipo} entradas para '{tipo}' pero NINGUNA con nivel='{nivel}'."))
            # mostrar qué niveles existen
            niveles_existentes = list(
                CatalogoMicroorganismo.objects.filter(marcador=tipo)
                .values_list("nivel", flat=True).distinct()
            )
            self.stdout.write(W(f"     Niveles existentes en catálogo: {niveles_existentes}"))
            self.stdout.write(W("     → El lookup filtra por nivel, por eso no hay coincidencias.\n"))

        # Muestra de entradas en catálogo
        self.stdout.write(f"\n  Primeras entradas (marcador='{tipo}', nivel='{nivel}'):")
        sample_cat = CatalogoMicroorganismo.objects.filter(
            marcador=tipo, nivel__iexact=nivel
        ).values("nombre","clasificacion")[:10]
        if sample_cat:
            for e in sample_cat:
                self.stdout.write(f"    · {e['nombre']!r:40s} → {e['clasificacion']}")
        else:
            self.stdout.write(W("    (ninguna — el nivel puede no coincidir exactamente)"))

        # ── 2. Datos en ResultadoTaxonomico ─────────────────────────────
        self.stdout.write(f"\n{S('RESULTADOS TAXONÓMICOS')}  (Top {top} por hits, tipo='{tipo}')")
        qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
        total_res = qs.count()
        self.stdout.write(f"  Total registros ResultadoTaxonomico: {total_res}")

        if total_res == 0:
            self.stdout.write(E("  ⚠  No hay resultados cargados para este marcador."))
            return

        top_taxa = list(
            qs.values(nombre=F(campo))
            .annotate(hits=Sum("num_hits"))
            .order_by("-hits")[:top]
        )

        # ── 3. Cruce con catálogo ───────────────────────────────────────
        # Lookup usando la misma lógica que el código de producción
        lookup_solo_marcador = {
            o.nombre.lower().strip(): o.clasificacion
            for o in CatalogoMicroorganismo.objects.filter(marcador=tipo)
        }
        lookup_marcador_nivel = {
            o.nombre.lower().strip(): o.clasificacion
            for o in CatalogoMicroorganismo.objects.filter(marcador=tipo, nivel__iexact=nivel)
        }
        lookup_solo_nivel = {
            o.nombre.lower().strip(): o.clasificacion
            for o in CatalogoMicroorganismo.objects.filter(nivel__iexact=nivel)
        }

        coincidencias_marcador = 0
        coincidencias_ambos    = 0
        sin_match              = []

        self.stdout.write(f"\n  {'Taxón':<40} {'solo marcador':>15} {'marcador+nivel':>16} {'solo nivel':>12}")
        self.stdout.write("  " + "-"*85)

        for t in top_taxa:
            nombre = (t["nombre"] or "").strip()
            key    = nombre.lower()

            m1 = lookup_solo_marcador.get(key, "—")
            m2 = lookup_marcador_nivel.get(key, "—")
            m3 = lookup_solo_nivel.get(key, "—")

            if m1 != "—": coincidencias_marcador += 1
            if m2 != "—": coincidencias_ambos    += 1
            if m1 == "—" and m2 == "—": sin_match.append(nombre)

            estado = "✓" if m2 != "—" else ("~" if m1 != "—" else "✗")
            linea  = f"  {estado} {nombre!r:<38} {m1:>15} {m2:>16} {m3:>12}"
            if m2 != "—":
                self.stdout.write(S(linea))
            elif m1 != "—":
                self.stdout.write(W(linea))
            else:
                self.stdout.write(E(linea))

        # ── 4. Resumen ──────────────────────────────────────────────────
        self.stdout.write(f"\n{S('RESUMEN')}")
        self.stdout.write(f"  Top {top} taxa analizados:              {len(top_taxa)}")
        self.stdout.write(f"  Coinciden solo por marcador:           {coincidencias_marcador}")
        self.stdout.write(f"  Coinciden por marcador+nivel:          {coincidencias_ambos}")
        self.stdout.write(f"  Sin coincidencia alguna:               {len(sin_match)}")

        if sin_match:
            self.stdout.write(W("\n  Taxones sin clasificar (primeros 10):"))
            for n in sin_match[:10]:
                self.stdout.write(W(f"    · {n!r}"))

        # ── 5. Recomendación ────────────────────────────────────────────
        self.stdout.write(f"\n{S('RECOMENDACIÓN')}")
        if coincidencias_ambos == 0 and coincidencias_marcador > 0:
            self.stdout.write(W(
                f"  Los nombres SÍ existen en el catálogo para marcador='{tipo}',\n"
                f"  pero el campo `nivel` no coincide con '{nivel}'.\n"
                f"  → Actualiza el campo `nivel` en el catálogo o ajusta el lookup."
            ))
        elif coincidencias_marcador == 0:
            self.stdout.write(E(
                f"  Ningún taxón del Top {top} tiene entrada en el catálogo.\n"
                f"  Causas posibles:\n"
                f"  1) El catálogo no tiene entradas para marcador='{tipo}'.\n"
                f"  2) Los nombres en el catálogo no coinciden con los del archivo.\n"
                f"     Ejemplo: catálogo tiene 'Bacillus' pero los datos tienen 'g__Bacillus'.\n"
                f"  3) El catálogo está vacío — agregar entradas desde el Admin."
            ))
        else:
            self.stdout.write(S(
                f"  El lookup funciona correctamente.\n"
                f"  {coincidencias_ambos}/{len(top_taxa)} taxa tienen clasificación en el catálogo."
            ))

        self.stdout.write("")

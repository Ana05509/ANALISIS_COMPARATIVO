from django.db import migrations

# Filas de encabezado de sección ("HONGOS" / "BACTERIAS") que quedaron
# guardadas como si fueran microorganismos reales en importaciones hechas
# antes de que el parser las filtrara — se ven duplicadas en la gráfica
# (barra fantasma sin valor) y en las tablas (que ya traen su propio
# encabezado "Bacterias"/"Hongos"). Coincide exactamente con el nombre y
# con no tener ningún valor UFC parseado, así que es seguro borrarlas sin
# tocar ningún recuento real.
NOMBRES_FANTASMA = ['HONGOS', 'BACTERIA', 'BACTERIAS', 'HONGO']


def limpiar_filas_fantasma(apps, schema_editor):
    RecuentoUFC = apps.get_model('bioquimica', 'RecuentoUFC')
    RecuentoUFC.objects.filter(
        nombre__iregex=r'^(%s)$' % '|'.join(NOMBRES_FANTASMA),
        coeficiente__isnull=True,
        menor_que_limite=False,
    ).delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bioquimica', '0002_add_archivo_pdf'),
    ]

    operations = [
        migrations.RunPython(limpiar_filas_fantasma, noop),
    ]

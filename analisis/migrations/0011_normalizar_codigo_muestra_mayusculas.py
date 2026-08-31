from django.db import migrations


class Migration(migrations.Migration):
    """
    Normaliza MuestraSuelo.codigo a mayúsculas para los registros ya
    existentes (ej. "Amazonico_16S", "Geisha_16s" → "AMAZONICO_16S",
    "GEISHA_16S") — de acá en adelante MuestraSuelo.save() y
    upload_service.procesar_upload() ya lo hacen solo, ver models.py.

    UPDATE en SQL directo (no vía el ORM/apps.get_model): no dispara el
    post_save de simple_history, así que no crea entradas de historial
    "código cambiado" por esta normalización — es una limpieza de formato,
    no un cambio de datos que un usuario haya hecho.

    Sin colisiones verificado antes de escribir esta migración (24
    muestras reales, ninguna pareja coincide al pasarla a mayúsculas).
    """

    dependencies = [
        ('analisis', '0010_alter_historicalmuestrasuelo_codigo_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="UPDATE analisis_muestrasuelo SET codigo = UPPER(codigo) WHERE codigo <> UPPER(codigo);",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

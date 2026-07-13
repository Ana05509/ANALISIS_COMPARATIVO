import unicodedata
from django.db import migrations, models


def _sin_tildes(texto):
    nfkd = unicodedata.normalize('NFD', texto)
    return ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')


MAPA_NIVEL = {
    # genus
    'genus': 'genus', 'genero': 'genus', 'gen': 'genus',
    # species
    'species': 'species', 'especie': 'species', 'specie': 'species',
    'sp': 'species', 'spp': 'species',
    # family
    'family': 'family', 'familia': 'family', 'fam': 'family',
    # order
    'order': 'order', 'orden': 'order', 'ord': 'order',
    # class
    'class': 'class', 'clase': 'class', 'cls': 'class',
    # phylum
    'phylum': 'phylum', 'filo': 'phylum', 'division': 'phylum',
    'division': 'phylum',
}


def normalizar_niveles(apps, schema_editor):
    CatalogoMicroorganismo = apps.get_model('analisis', 'CatalogoMicroorganismo')
    for obj in CatalogoMicroorganismo.objects.all():
        clave = _sin_tildes(obj.nivel.strip().lower())
        nuevo = MAPA_NIVEL.get(clave)
        if nuevo and nuevo != obj.nivel:
            obj.nivel = nuevo
            obj.save(update_fields=['nivel'])


class Migration(migrations.Migration):

    dependencies = [
        ('analisis', '0002_usuario_avatar'),
    ]

    operations = [
        migrations.RunPython(normalizar_niveles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='catalogomicroorganismo',
            name='nivel',
            field=models.CharField(
                choices=[
                    ('genus',   'Género'),
                    ('species', 'Especie'),
                    ('family',  'Familia'),
                    ('order',   'Orden'),
                    ('class',   'Clase'),
                    ('phylum',  'Filo'),
                ],
                db_index=True,
                max_length=50,
                verbose_name='Nivel Taxonómico',
                help_text='Nivel taxonómico canónico del organismo',
            ),
        ),
    ]

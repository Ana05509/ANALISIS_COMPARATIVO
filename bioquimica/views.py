import json
from datetime import date

import plotly.graph_objects as go
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render, get_object_or_404

from .models import (
    EnsayoMicrobiologico, RecuentoUFC,
    MicroorganismoAislado, PruebaBioquimica,
)


def _grafico_recuento(ensayo):
    recuentos = list(ensayo.recuentos.all())
    if not recuentos:
        return None

    nombres = [r.nombre for r in recuentos]
    valores = [max(r.valor_numerico, 0.1) for r in recuentos]
    etiquetas = [r.valor_display for r in recuentos]
    colores = ['#1D9E75' if r.tipo_organismo == 'bacteria' else '#F5A623' for r in recuentos]

    fig = go.Figure(go.Bar(
        x=nombres,
        y=valores,
        text=etiquetas,
        textposition='outside',
        marker_color=colores,
        hovertemplate='<b>%{x}</b><br>%{text}<extra></extra>',
    ))

    fig.update_layout(
        yaxis_type='log',
        yaxis_title='UFC/g (escala logarítmica)',
        xaxis_title='Microorganismo',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family='Inter, sans-serif', size=12),
        margin=dict(t=20, b=120, l=60, r=20),
        xaxis=dict(tickangle=-35),
        showlegend=False,
        height=420,
    )

    return json.loads(fig.to_json())


def _grafico_heatmap_pruebas(ensayo):
    aislados = list(ensayo.aislados.prefetch_related('pruebas').filter(pruebas__isnull=False).distinct())
    if not aislados:
        return None

    # Collect all unique test names (union across all organisms)
    todas_pruebas = []
    vistas = set()
    for org in aislados:
        for p in org.pruebas.all():
            if p.nombre_prueba not in vistas:
                todas_pruebas.append(p.nombre_prueba)
                vistas.add(p.nombre_prueba)

    if not todas_pruebas:
        return None

    organismos = [o.nombre_cientifico for o in aislados]

    # Build matrix: 1=positive, -1=negative, 0=neutral/text
    matriz = []
    textos = []
    for org in aislados:
        pruebas_dict = {p.nombre_prueba: p.resultado for p in org.pruebas.all()}
        fila_val = []
        fila_txt = []
        for nombre in todas_pruebas:
            res = pruebas_dict.get(nombre, '—')
            fila_txt.append(res)
            r = res.strip().lower()
            if r in ('+', 'c', 'crecimiento'):
                fila_val.append(1)
            elif r in ('-', 'nc', 'no hay crecimiento'):
                fila_val.append(-1)
            else:
                fila_val.append(0)
        matriz.append(fila_val)
        textos.append(fila_txt)

    fig = go.Figure(go.Heatmap(
        z=matriz,
        x=todas_pruebas,
        y=organismos,
        text=textos,
        texttemplate='%{text}',
        colorscale=[
            [0.0, '#FAEEDA'],
            [0.5, '#F1EFE8'],
            [1.0, '#E1F5EE'],
        ],
        showscale=False,
        hovertemplate='<b>%{y}</b><br>%{x}: <b>%{text}</b><extra></extra>',
        zmin=-1, zmax=1,
    ))

    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family='Inter, sans-serif', size=11),
        margin=dict(t=20, b=140, l=160, r=20),
        xaxis=dict(tickangle=-40, side='bottom'),
        height=max(300, len(organismos) * 60 + 180),
    )

    return json.loads(fig.to_json())


@login_required
def lista_ensayos(request):
    tipo_filtro = request.GET.get('tipo', '')
    qs = EnsayoMicrobiologico.objects.all()
    if tipo_filtro in ('recuento', 'aislamiento'):
        qs = qs.filter(tipo=tipo_filtro)

    context = {
        'ensayos': qs,
        'tipo_filtro': tipo_filtro,
        'total_recuento': EnsayoMicrobiologico.objects.filter(tipo='recuento').count(),
        'total_aislamiento': EnsayoMicrobiologico.objects.filter(tipo='aislamiento').count(),
    }
    return render(request, 'bioquimica/lista.html', context)


def _clasificacion_catalogo(aislados):
    """
    Retorna un dict {aislado.pk: clasificacion} consultando CatalogoMicroorganismo
    con el marcador correcto según el tipo de organismo (bacteria→16S, hongo→ITS).
    """
    from analisis.models import CatalogoMicroorganismo

    TIPO_A_MARCADOR = {'bacteria': '16S', 'hongo': 'ITS'}

    # Agrupar PKs por marcador para hacer solo 2 queries al catálogo como máximo
    pks_por_marcador = {'16S': [], 'ITS': []}
    genero_por_pk = {}
    for a in aislados:
        marcador = TIPO_A_MARCADOR.get(a.tipo, '16S')
        pks_por_marcador[marcador].append(a.pk)
        genero_por_pk[a.pk] = (a.genero or '').strip().lower()

    resultado = {}
    for marcador, pks in pks_por_marcador.items():
        if not pks:
            continue
        lookup = {
            obj.nombre.lower(): obj.clasificacion
            for obj in CatalogoMicroorganismo.objects.filter(nivel='genus', marcador=marcador)
        }
        for pk in pks:
            genero = genero_por_pk.get(pk, '')
            resultado[pk] = lookup.get(genero, 'sin_clasificar') if genero else 'sin_clasificar'

    return resultado


@login_required
def detalle_ensayo(request, pk):
    ensayo = get_object_or_404(EnsayoMicrobiologico, pk=pk)

    grafico_recuento_json = None
    grafico_heatmap_json = None

    if ensayo.tipo == 'recuento':
        datos = _grafico_recuento(ensayo)
        grafico_recuento_json = json.dumps(datos) if datos else None
    else:
        datos = _grafico_heatmap_pruebas(ensayo)
        grafico_heatmap_json = json.dumps(datos) if datos else None

    aislados_con_pruebas = None
    aislados_sin_pruebas = None
    clasificacion_por_pk = {}
    if ensayo.tipo == 'aislamiento':
        aislados_con_pruebas = list(
            ensayo.aislados.filter(pruebas__isnull=False).distinct().prefetch_related('pruebas')
        )
        aislados_sin_pruebas = list(ensayo.aislados.filter(pruebas__isnull=True))
        todos_aislados = aislados_con_pruebas + aislados_sin_pruebas
        clasificacion_por_pk = _clasificacion_catalogo(todos_aislados)
        for a in todos_aislados:
            a.clasificacion_catalogo = clasificacion_por_pk.get(a.pk, 'sin_clasificar')

    context = {
        'ensayo': ensayo,
        'grafico_recuento_json': grafico_recuento_json,
        'grafico_heatmap_json': grafico_heatmap_json,
        'recuentos_hongos': ensayo.recuentos.filter(tipo_organismo='hongo') if ensayo.tipo == 'recuento' else None,
        'recuentos_bacterias': ensayo.recuentos.filter(tipo_organismo='bacteria') if ensayo.tipo == 'recuento' else None,
        'aislados_con_pruebas': aislados_con_pruebas,
        'aislados_sin_pruebas': aislados_sin_pruebas,
    }
    return render(request, 'bioquimica/detalle.html', context)


@login_required
def subir_pdf(request):
    if request.method != 'POST':
        return render(request, 'bioquimica/subir_pdf.html')

    archivo = request.FILES.get('archivo')
    if not archivo:
        messages.error(request, "Debe seleccionar un archivo PDF.")
        return render(request, 'bioquimica/subir_pdf.html')

    if not archivo.name.lower().endswith('.pdf'):
        messages.error(request, "El archivo debe tener extensión .pdf.")
        return render(request, 'bioquimica/subir_pdf.html')

    try:
        from .services.pdf_parser import parsear_pdf
        resultado = parsear_pdf(archivo)
    except Exception as e:
        messages.error(request, f"No se pudo leer el PDF: {e}")
        return render(request, 'bioquimica/subir_pdf.html')

    header = resultado['header']
    codigo = header.get('codigo')

    if not codigo:
        messages.error(request, "No se encontró el código del ensayo en el PDF (ej: MAg-225-2023).")
        return render(request, 'bioquimica/subir_pdf.html')

    if EnsayoMicrobiologico.objects.filter(codigo=codigo).exists():
        messages.warning(request, f"El ensayo '{codigo}' ya existe en el sistema.")
        ensayo = EnsayoMicrobiologico.objects.get(codigo=codigo)
        return redirect('bioquimica:detalle', pk=ensayo.pk)

    def _fecha(valor):
        if not valor:
            return date.today()
        try:
            from datetime import datetime
            return datetime.strptime(valor, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return date.today()

    try:
        with transaction.atomic():
            ensayo = EnsayoMicrobiologico(
                codigo=codigo,
                tipo=resultado['tipo'],
                nombre_muestra=header.get('nombre_muestra', 'Muestra'),
                etiqueta=header.get('etiqueta', ''),
                fecha_recepcion=_fecha(header.get('fecha_recepcion')),
                fecha_ejecucion=_fecha(header.get('fecha_ejecucion')),
                fecha_reporte=_fecha(header.get('fecha_reporte')),
                temp_ambiental=header.get('temp_ambiental'),
                humedad_ambiental=header.get('humedad_ambiental'),
                registrado_por=request.user,
            )
            archivo.seek(0)
            ensayo.archivo_pdf.save(archivo.name, archivo, save=False)
            ensayo.save()

            if resultado['tipo'] == 'recuento':
                RecuentoUFC.objects.bulk_create([
                    RecuentoUFC(ensayo=ensayo, **d)
                    for d in resultado['datos']
                ])
                total = len(resultado['datos'])
            else:
                total = 0
                for org_data in resultado['datos']:
                    taxonomia = org_data.pop('taxonomia', {})
                    pruebas   = org_data.pop('pruebas', [])
                    org = MicroorganismoAislado(ensayo=ensayo, **org_data, **taxonomia)
                    org.save()
                    if pruebas:
                        PruebaBioquimica.objects.bulk_create([
                            PruebaBioquimica(microorganismo=org, **p)
                            for p in pruebas
                        ])
                    total += 1

        messages.success(
            request,
            f"PDF procesado: ensayo {codigo} creado con {total} "
            f"{'registros UFC/g' if resultado['tipo'] == 'recuento' else 'organismos aislados'}."
        )
        return redirect('bioquimica:detalle', pk=ensayo.pk)

    except Exception as e:
        messages.error(request, f"Error al guardar los datos: {e}")
        return render(request, 'bioquimica/subir_pdf.html')

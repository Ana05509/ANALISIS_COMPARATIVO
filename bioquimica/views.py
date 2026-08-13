import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast

import plotly.graph_objects as go
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render, get_object_or_404

from .forms import EnsayoManualForm
from .models import (
    EnsayoMicrobiologico, RecuentoUFC, ParametroRecuento,
    MicroorganismoAislado, PruebaBioquimica,
)
from analisis.audit import registrar_accion
from django.contrib.admin.models import ADDITION


def _grafico_recuento(ensayo):
    # Filas sin valor UFC estándar (tipo_organismo='otro', o cualquier fila
    # cargada solo con ParametroRecuento libres) no tienen nada que graficar
    # en escala logarítmica — antes caían igual con valor_numerico=0 (piso
    # artificial de 0.1 más abajo) y aparecían como una barra fantasma con
    # etiqueta "—". Se descartan acá, no en el JS: sus datos reales se ven
    # en la tabla de detalle, no en este gráfico.
    recuentos = [r for r in ensayo.recuentos.all() if r.menor_que_limite or r.coeficiente is not None]
    if not recuentos:
        return None

    nombres = [r.nombre for r in recuentos]
    valores = [max(r.valor_numerico, 0.1) for r in recuentos]
    etiquetas = [r.valor_display for r in recuentos]
    colores = ['#1D9E75' if r.tipo_organismo == 'bacteria' else '#F5A623' for r in recuentos]
    # tipo_organismo por punto — el cliente lo usa para recolorear en modo
    # Escala de grises sin perder la agrupación bacteria/hongo (ver
    # ChartTheme en detalle.html); no afecta el color/valor mostrado en modo Color.
    tipos = [r.tipo_organismo for r in recuentos]

    fig = go.Figure(go.Bar(
        x=nombres,
        y=valores,
        text=etiquetas,
        textposition='outside',
        marker_color=colores,
        customdata=tipos,
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

    # fig.to_json() no está anotado en los stubs de plotly y Pylance infiere
    # un retorno "str | Any | None" — en runtime, para una Figure ya armada
    # con datos (como acá) siempre devuelve el JSON como str; el cast no
    # cambia nada en tiempo de ejecución, solo se lo aclara al chequeador.
    return json.loads(cast(str, fig.to_json()))


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
            [0.0, '#FDBA74'],   # naranja-300 → negativo
            [0.5, '#E5E7EB'],   # gris-200    → neutro
            [1.0, '#86EFAC'],   # verde-300   → positivo
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

    # fig.to_json() no está anotado en los stubs de plotly y Pylance infiere
    # un retorno "str | Any | None" — en runtime, para una Figure ya armada
    # con datos (como acá) siempre devuelve el JSON como str; el cast no
    # cambia nada en tiempo de ejecución, solo se lo aclara al chequeador.
    return json.loads(cast(str, fig.to_json()))


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
        'recuentos_hongos': ensayo.recuentos.filter(tipo_organismo='hongo').prefetch_related('parametros') if ensayo.tipo == 'recuento' else None,
        'recuentos_bacterias': ensayo.recuentos.filter(tipo_organismo='bacteria').prefetch_related('parametros') if ensayo.tipo == 'recuento' else None,
        'recuentos_otros': ensayo.recuentos.filter(tipo_organismo='otro').prefetch_related('parametros') if ensayo.tipo == 'recuento' else None,
        'aislados_con_pruebas': aislados_con_pruebas,
        'aislados_sin_pruebas': aislados_sin_pruebas,
    }
    return render(request, 'bioquimica/detalle.html', context)


def _fecha(valor):
    if not valor:
        return date.today()
    try:
        from datetime import datetime
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return date.today()


def _guardar_ensayo(archivo, request):
    """
    Parsea y guarda un PDF. Retorna (ensayo, msg_ok) o lanza ValueError/Exception.
    Raises ValueError con mensaje amigable para duplicados y errores de validación.
    """
    from .services.pdf_parser import parsear_pdf

    if not archivo.name.lower().endswith('.pdf'):
        raise ValueError(f"«{archivo.name}» no es un PDF.")

    try:
        resultado = parsear_pdf(archivo)
    except Exception as e:
        raise ValueError(f"No se pudo leer «{archivo.name}»: {e}")

    header = resultado['header']
    codigo = header.get('codigo')
    if not codigo:
        raise ValueError(f"«{archivo.name}»: no se encontró código MAg-XXX-XXXX.")

    if EnsayoMicrobiologico.objects.filter(codigo=codigo).exists():
        existing = EnsayoMicrobiologico.objects.get(codigo=codigo)
        raise _DuplicadoError(codigo, existing.pk)

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
                RecuentoUFC(ensayo=ensayo, **d) for d in resultado['datos']
            ])
        else:
            for org_data in resultado['datos']:
                taxonomia = org_data.pop('taxonomia', {})
                pruebas   = org_data.pop('pruebas', [])
                org = MicroorganismoAislado(ensayo=ensayo, **org_data, **taxonomia)
                org.save()
                if pruebas:
                    PruebaBioquimica.objects.bulk_create([
                        PruebaBioquimica(microorganismo=org, **p) for p in pruebas
                    ])

    return ensayo


class _DuplicadoError(Exception):
    def __init__(self, codigo, pk):
        self.codigo = codigo
        self.pk = pk


@login_required
def subir_pdf(request):
    if request.method != 'POST':
        return render(request, 'bioquimica/subir_pdf.html')

    archivos = request.FILES.getlist('archivos')
    if not archivos:
        messages.error(request, "Debe seleccionar al menos un archivo PDF.")
        return render(request, 'bioquimica/subir_pdf.html')

    creados = []      # [(codigo, pk), ...]
    duplicados = []   # [codigo, ...]
    errores = []      # [mensaje, ...]

    for archivo in archivos:
        try:
            ensayo = _guardar_ensayo(archivo, request)
            registrar_accion(
                request, ensayo,
                f"Ensayo importado desde PDF ({archivo.name}).",
                accion=ADDITION,
            )
            creados.append((ensayo.codigo, ensayo.pk))
        except _DuplicadoError as e:
            duplicados.append(e.codigo)
        except (ValueError, Exception) as e:
            errores.append(str(e))

    if creados:
        lista = ', '.join(c for c, _ in creados)
        messages.success(request, f"{len(creados)} ensayo(s) importado(s): {lista}.")
    if duplicados:
        lista = ', '.join(duplicados)
        messages.warning(request, f"{len(duplicados)} ya existente(s) omitido(s): {lista}.")
    for msg in errores:
        messages.error(request, msg)

    if len(creados) == 1 and not duplicados and not errores:
        return redirect('bioquimica:detalle', pk=creados[0][1])

    if not creados and not duplicados and not errores:
        return render(request, 'bioquimica/subir_pdf.html')

    return redirect('bioquimica:lista')


# ─── Ingreso manual (alternativa a subir PDF) ──────────────────────────────
#
# Para reportes cuya estructura no coincide con la que espera pdf_parser.py
# (otro formato de laboratorio, PDF escaneado sin capa de texto, etc.): en
# vez de intentar leer el documento, la persona transcribe los valores a
# mano en un formulario con los mismos campos que ya usa el sistema. El PDF
# original se puede adjuntar igual como respaldo (campo archivo_pdf), pero
# ya no es la fuente de la que se extraen los datos.

def _decimal_o_none(valor):
    valor = (valor or '').strip().replace(',', '.')
    if not valor:
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None


def _int_o_none(valor):
    valor = (valor or '').strip()
    if not valor:
        return None
    try:
        return int(valor)
    except ValueError:
        return None


def _parsear_recuento_manual(post):
    """
    Filas de recuento UFC/g ingresadas a mano. Cada fila tiene sus campos
    fijos sufijados por índice (rec_nombre_0, rec_coeficiente_0, …) y sus
    parámetros adicionales libres en arrays paralelos sufijados con el mismo
    índice (recparam_nombre_0[], recparam_valor_0[], …) — mismo patrón
    indexado que _parsear_aislamiento_manual usa para organismo/pruebas,
    generado por el JS del template al agregar/quitar tarjetas y parámetros.
    """
    filas = []
    i = 0
    while f'rec_nombre_{i}' in post:
        nombre = (post.get(f'rec_nombre_{i}') or '').strip()
        if not nombre:
            i += 1
            continue

        menor = post.get(f'rec_menor_{i}', 'no') == 'si'
        fila = {
            'tipo_organismo':   post.get(f'rec_tipo_{i}', 'bacteria'),
            'nombre':           nombre,
            'coeficiente':      None if menor else _decimal_o_none(post.get(f'rec_coeficiente_{i}', '')),
            'exponente':        None if menor else _int_o_none(post.get(f'rec_exponente_{i}', '')),
            'menor_que_limite': menor,
        }

        numeros = post.getlist(f'recparam_numero_{i}[]')
        nombres_p = post.getlist(f'recparam_nombre_{i}[]')
        valores_p = post.getlist(f'recparam_valor_{i}[]')
        parametros = []
        siguiente = 1
        for j, nombre_param in enumerate(nombres_p):
            nombre_param = (nombre_param or '').strip()
            if not nombre_param:
                continue
            valor = (valores_p[j] or '').strip() if j < len(valores_p) else ''
            numero = _int_o_none(numeros[j] if j < len(numeros) else '') or siguiente
            parametros.append({'numero': numero, 'nombre': nombre_param, 'valor': valor or '—'})
            siguiente += 1
        fila['parametros'] = parametros

        filas.append(fila)
        i += 1

    return filas


def _parsear_aislamiento_manual(post):
    """
    Organismos aislados ingresados a mano. Cada organismo tiene sus campos
    de taxonomía sufijados por índice (org_nombre_0, org_dominio_0, …) y sus
    pruebas bioquímicas en arrays paralelos sufijados con el mismo índice
    (prueba_nombre_0[], prueba_resultado_0[], …), generados por el JS del
    template al agregar/quitar organismos y pruebas dinámicamente.
    """
    organismos = []
    i = 0
    while f'org_nombre_{i}' in post:
        nombre = (post.get(f'org_nombre_{i}') or '').strip()
        if not nombre:
            i += 1
            continue

        org_data = {
            'tipo':              post.get(f'org_tipo_{i}', 'bacteria'),
            'nombre_cientifico': nombre,
            'dominio':           (post.get(f'org_dominio_{i}') or '').strip(),
            'filo':              (post.get(f'org_filo_{i}') or '').strip(),
            'clase':             (post.get(f'org_clase_{i}') or '').strip(),
            'orden_taxonomico':  (post.get(f'org_orden_{i}') or '').strip(),
            'familia':           (post.get(f'org_familia_{i}') or '').strip(),
            'genero':            (post.get(f'org_genero_{i}') or '').strip(),
            'especie':           (post.get(f'org_especie_{i}') or '').strip(),
        }

        numeros    = post.getlist(f'prueba_numero_{i}[]')
        nombres_p  = post.getlist(f'prueba_nombre_{i}[]')
        resultados = post.getlist(f'prueba_resultado_{i}[]')
        pruebas = []
        siguiente = 1
        for j, nombre_prueba in enumerate(nombres_p):
            nombre_prueba = (nombre_prueba or '').strip()
            if not nombre_prueba:
                continue
            resultado = (resultados[j] or '').strip() if j < len(resultados) else ''
            numero = _int_o_none(numeros[j] if j < len(numeros) else '') or siguiente
            pruebas.append({'numero': numero, 'nombre_prueba': nombre_prueba, 'resultado': resultado or '—'})
            siguiente += 1
        org_data['pruebas'] = pruebas

        organismos.append(org_data)
        i += 1

    return organismos


@login_required
def ingreso_manual(request):
    if request.user.rol == 'estudiante':
        messages.error(
            request,
            "Su nivel de cuenta no dispone de permisos para registrar ensayos. "
            "Si es docente o investigador, contacte al administrador del sistema para actualizar su rol."
        )
        return redirect("bioquimica:lista")

    if request.method != 'POST':
        return render(request, 'bioquimica/ingreso_manual.html', {'form': EnsayoManualForm()})

    form = EnsayoManualForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, 'bioquimica/ingreso_manual.html', {'form': form})

    codigo = form.cleaned_data['codigo']
    if EnsayoMicrobiologico.objects.filter(codigo=codigo).exists():
        form.add_error('codigo', 'Ya existe un ensayo con este código.')
        return render(request, 'bioquimica/ingreso_manual.html', {'form': form})

    tipo = form.cleaned_data['tipo']

    try:
        with transaction.atomic():
            ensayo = EnsayoMicrobiologico(
                codigo=codigo,
                tipo=tipo,
                nombre_muestra=form.cleaned_data['nombre_muestra'],
                etiqueta=form.cleaned_data.get('etiqueta') or '',
                fecha_recepcion=form.cleaned_data['fecha_recepcion'],
                fecha_ejecucion=form.cleaned_data['fecha_ejecucion'],
                fecha_reporte=form.cleaned_data['fecha_reporte'],
                temp_ambiental=form.cleaned_data.get('temp_ambiental'),
                humedad_ambiental=form.cleaned_data.get('humedad_ambiental'),
                observaciones=form.cleaned_data.get('observaciones') or '',
                registrado_por=request.user,
            )
            archivo_pdf = form.cleaned_data.get('archivo_pdf')
            if archivo_pdf:
                ensayo.archivo_pdf = archivo_pdf
            ensayo.save()

            if tipo == 'recuento':
                filas = _parsear_recuento_manual(request.POST)
                if not filas:
                    raise ValueError("Agrega al menos un microorganismo con su recuento UFC/g.")
                for i, f in enumerate(filas):
                    parametros = f.pop('parametros')
                    r = RecuentoUFC(ensayo=ensayo, orden=i, **f)
                    r.save()
                    if parametros:
                        ParametroRecuento.objects.bulk_create([
                            ParametroRecuento(recuento=r, **p) for p in parametros
                        ])
            else:
                organismos = _parsear_aislamiento_manual(request.POST)
                if not organismos:
                    raise ValueError("Agrega al menos un microorganismo aislado.")
                for org_data in organismos:
                    pruebas = org_data.pop('pruebas')
                    org = MicroorganismoAislado(ensayo=ensayo, **org_data)
                    org.save()
                    if pruebas:
                        PruebaBioquimica.objects.bulk_create([
                            PruebaBioquimica(microorganismo=org, **p) for p in pruebas
                        ])
    except ValueError as e:
        messages.error(request, str(e))
        return render(request, 'bioquimica/ingreso_manual.html', {'form': form})

    registrar_accion(request, ensayo, "Ensayo registrado manualmente (sin PDF).", accion=ADDITION)
    messages.success(request, f"Ensayo {ensayo.codigo} registrado manualmente.")
    return redirect('bioquimica:detalle', pk=ensayo.pk)

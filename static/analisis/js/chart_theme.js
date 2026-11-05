/*
 * ChartTheme — estilo compartido de las gráficas (Plotly.js y Chart.js):
 * paletas color/grises, patrones, layout base, rango Y y descarga PNG/SVG.
 */
(function (global) {
    'use strict';

    var MODES = { COLOR: 'color', GRISES: 'grises', PUBLICACION: 'publicacion' };

    var PALETTE_COLOR = [
        '#1D9E75', '#BA7517', '#185FA5', '#A32D2D', '#0F6E56', '#6B4E9E',
        '#0C447C', '#5F5E5A', '#E07B39', '#264653', '#E9C46A', '#3A86FF'
    ];

    // Grises con salto de luminosidad suficiente para distinguirse en pantalla e impresión.
    var PALETTE_GRAY = [
        '#1a1a1a', '#3d3d3d', '#5c5c5c', '#787878',
        '#969696', '#b0b0b0', '#c8c8c8', '#e0e0e0'
    ];

    var PATTERNS = ['', '/', '\\', 'x', '.', '|', '-', '+'];
    var MARKER_SYMBOLS = ['circle', 'square', 'diamond', 'triangle-up', 'cross', 'x', 'triangle-down', 'star'];
    var DASH_STYLES = ['solid', 'dot', 'dash', 'longdash', 'dashdot', 'longdashdot'];

    function isGrayMode(mode) { return mode === MODES.GRISES || mode === MODES.PUBLICACION; }

    function getColor(mode, i) {
        var pal = isGrayMode(mode) ? PALETTE_GRAY : PALETTE_COLOR;
        return pal[i % pal.length];
    }
    function getPattern(i) { return PATTERNS[i % PATTERNS.length]; }
    function getSymbol(i) { return MARKER_SYMBOLS[i % MARKER_SYMBOLS.length]; }
    function getDash(i) { return DASH_STYLES[i % DASH_STYLES.length]; }

    /** Muestra "Unclassified" en español (solo en pantalla, como el filtro taxon_legible). */
    function taxonLegible(nombre) {
        if (!nombre) return nombre;
        return String(nombre).trim().toLowerCase() === 'unclassified' ? 'Sin identificar' : nombre;
    }

    /** Convierte un color hex a su equivalente en gris perceptual (luminancia). */
    function toGrayscaleHex(hex) {
        if (!hex || hex[0] !== '#') return hex;
        var h = hex.replace('#', '');
        if (h.length === 3) h = h.split('').map(function (c) { return c + c; }).join('');
        var r = parseInt(h.substr(0, 2), 16), g = parseInt(h.substr(2, 2), 16), b = parseInt(h.substr(4, 2), 16);
        var y = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
        var yy = y.toString(16).padStart(2, '0');
        return '#' + yy + yy + yy;
    }

    /** Aplica color y patrón por índice de trace (una categoría o muestra por trace). */
    function styleTracesByIndex(data, mode) {
        if (!Array.isArray(data)) return data;
        data.forEach(function (trace, i) {
            var color = getColor(mode, i);
            trace.marker = trace.marker || {};
            if (trace.type === 'bar') {
                trace.marker.color = color;
                if (isGrayMode(mode)) {
                    trace.marker.pattern = { shape: getPattern(i), fgcolor: '#ffffff', bgcolor: color, size: 6 };
                } else {
                    trace.marker.pattern = undefined;
                }
            } else if (trace.type === 'scatter' || trace.mode) {
                trace.marker.color = color;
                if (isGrayMode(mode)) {
                    trace.marker.symbol = getSymbol(i);
                }
                if (trace.line) {
                    trace.line.color = color;
                    if (isGrayMode(mode)) trace.line.dash = getDash(i);
                }
            } else {
                trace.marker.color = color;
            }
        });
        return data;
    }

    /** Colorscale de heatmap según modo. */
    function heatmapColorscale(mode) {
        return isGrayMode(mode) ? 'Greys' : 'Viridis';
    }

    /** Layout base con cuadrícula horizontal. El modo "publicacion" usa Arial/Helvetica y texto más grande. */
    /** "publicacion" usa fondo blanco; "color"/"grises" siguen el tema claro/oscuro. */
    function isDarkTheme() {
        return document.documentElement.getAttribute('data-theme') === 'dark';
    }

    function baseLayout(mode) {
        var pub = mode === MODES.PUBLICACION;
        var dark = !pub && isDarkTheme();
        return {
            template: 'plotly_white',
            font: {
                family: pub ? 'Arial, Helvetica, sans-serif' : 'Outfit, sans-serif',
                size: pub ? 15 : 12,
                color: pub ? '#000000' : (dark ? '#edecea' : '#374151')
            },
            paper_bgcolor: pub ? '#ffffff' : (dark ? '#1c1b19' : undefined),
            plot_bgcolor: pub ? '#ffffff' : (dark ? '#1c1b19' : undefined),
        };
    }

    /** Acorta una etiqueta larga con "…" (solo en el eje, el dato no cambia). */
    function truncateLabel(text, maxLen) {
        var s = String(text == null ? '' : text);
        maxLen = maxLen || 22;
        return s.length > maxLen ? s.slice(0, maxLen - 1) + '…' : s;
    }

    /** {tickvals, ticktext} para un eje categórico con etiquetas truncadas a `maxLen`. */
    function buildTruncatedTicks(categorias, maxLen) {
        var vals = Array.from(new Set(categorias));
        return {
            tickvals: vals,
            ticktext: vals.map(function (c) { return truncateLabel(c, maxLen); }),
        };
    }

    /** A partir de este número de barras no se imprime el % (queda en el hover). */
    var DENSE_BAR_THRESHOLD = 32;
    function shouldShowBarText(nCategorias, nSeries) {
        return (nCategorias * (nSeries || 1)) <= DENSE_BAR_THRESHOLD;
    }

    /** Ancho de referencia (doble columna, mm) y DPI mínimo aceptados por la
     * mayoría de revistas científicas (Elsevier/Springer/MDPI/Frontiers). */
    var PUB_WIDTH_MM = 174;
    var PUB_DPI = 300;

    // Utilidades PNG: inyecta el chunk pHYs (resolución real)
    // Un PNG exportado desde un <canvas> no lleva DPI en sus metadatos (los
    // lectores asumen 96 DPI), lo que hace que revistas y verificadores
    // automáticos de figuras lo rechacen aunque el PNG tenga suficientes
    // píxeles. Esto inserta el chunk estándar PNG "pHYs" (resolución física)
    // justo después de IHDR, que siempre es el primer chunk de 25 bytes tras
    // la firma de 8 bytes — no altera ni un píxel de la imagen.
    var _CRC_TABLE = null;
    function _crc32(bytes) {
        if (!_CRC_TABLE) {
            _CRC_TABLE = [];
            for (var n = 0; n < 256; n++) {
                var c = n;
                for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
                _CRC_TABLE[n] = c >>> 0;
            }
        }
        var crc = 0xFFFFFFFF;
        for (var i = 0; i < bytes.length; i++) crc = _CRC_TABLE[(crc ^ bytes[i]) & 0xFF] ^ (crc >>> 8);
        return (crc ^ 0xFFFFFFFF) >>> 0;
    }

    function _buildPhysChunk(dpi) {
        var pxPerMeter = Math.round(dpi / 0.0254);
        var typeAndData = new Uint8Array(4 + 9);
        typeAndData.set([0x70, 0x48, 0x59, 0x73], 0); // 'pHYs'
        new DataView(typeAndData.buffer).setUint32(4, pxPerMeter, false);
        new DataView(typeAndData.buffer).setUint32(8, pxPerMeter, false);
        typeAndData[12] = 1; // unidad: metros
        var crc = _crc32(typeAndData);
        var chunk = new Uint8Array(4 + typeAndData.length + 4);
        new DataView(chunk.buffer).setUint32(0, 9, false); // longitud de los datos (sin type/crc)
        chunk.set(typeAndData, 4);
        new DataView(chunk.buffer).setUint32(4 + typeAndData.length, crc, false);
        return chunk;
    }

    /** Embebe la resolución real (DPI) en un Blob PNG. Devuelve un nuevo Blob. */
    function addPngDpi(blob, dpi) {
        return blob.arrayBuffer().then(function (buf) {
            var bytes = new Uint8Array(buf);
            var ihdrEnd = 8 + 25; // firma PNG (8) + chunk IHDR completo (siempre 25 bytes)
            var phys = _buildPhysChunk(dpi);
            var out = new Uint8Array(bytes.length + phys.length);
            out.set(bytes.subarray(0, ihdrEnd), 0);
            out.set(phys, ihdrEnd);
            out.set(bytes.subarray(ihdrEnd), ihdrEnd + phys.length);
            return new Blob([out], { type: 'image/png' });
        });
    }

    function _downloadBlob(blob, filename) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    }

    /** Overrides de eje Y para asegurar cuadrícula completa y sobria. */
    function yAxisGrid(mode) {
        var pub = mode === MODES.PUBLICACION;
        return {
            showgrid: true,
            // Gris sólido y opaco — el valor anterior (rgba con 35% de opacidad)
            // quedaba casi invisible sobre el fondo blanco. Sigue siendo sobrio,
            // pero ahora se nota a simple vista sin tener que acercarse a la
            // pantalla. En modo oscuro (fuera de "publicación", que siempre es
            // fondo blanco) se usa un gris más tenue para que no compita con
            // el fondo oscuro del gráfico.
            gridcolor: (!pub && isDarkTheme()) ? '#3a3833' : '#c8c8c8',
            gridwidth: 1,
            zeroline: false,
        };
    }

    /** Decodifica arrays binarios de Plotly ({dtype, bdata}) a arrays normales. */
    function _decodeTypedArray(obj) {
        if (!obj || typeof obj !== 'object' || typeof obj.bdata !== 'string') return null;
        var binary = atob(obj.bdata);
        var bytes = new Uint8Array(binary.length);
        for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        switch (obj.dtype) {
            case 'f8': return Array.from(new Float64Array(bytes.buffer));
            case 'f4': return Array.from(new Float32Array(bytes.buffer));
            case 'i4': return Array.from(new Int32Array(bytes.buffer));
            case 'i2': return Array.from(new Int16Array(bytes.buffer));
            case 'i1': return Array.from(new Int8Array(bytes.buffer));
            case 'u4': return Array.from(new Uint32Array(bytes.buffer));
            case 'u2': return Array.from(new Uint16Array(bytes.buffer));
            case 'u1': return Array.from(new Uint8Array(bytes.buffer));
            default:   return null;
        }
    }

    /** Devuelve un array plano de números a partir de un campo x/y/z de una
     * trace de Plotly, sea un array normal o el formato binario compacto. */
    function extractArray(field) {
        if (Array.isArray(field)) return field;
        return _decodeTypedArray(field) || [];
    }

    /** Rango [0, niceMax] redondeado al siguiente múltiplo limpio (1/2/5 × 10^n). */
    function computeYRange(values, opts) {
        opts = opts || {};
        var extraFrac = opts.headroomFrac || 0; // por si algún llamador necesita margen adicional
        var flat = (values || []).filter(function (v) { return typeof v === 'number' && isFinite(v); });
        if (!flat.length) return undefined;
        var max = Math.max.apply(null, flat);
        if (max <= 0) return undefined;
        var base = max * (1 + extraFrac);

        var magnitude = Math.pow(10, Math.floor(Math.log10(base)));
        var normalized = base / magnitude; // entre 1 y 10
        var niceStep;
        if (normalized <= 1) niceStep = 0.2 * magnitude;
        else if (normalized <= 2) niceStep = 0.5 * magnitude;
        else if (normalized <= 5) niceStep = 1 * magnitude;
        else niceStep = 2 * magnitude;

        var niceMax = Math.ceil(base / niceStep) * niceStep;
        if (niceMax <= base) niceMax += niceStep; // garantiza que la línea quede POR ENCIMA del máximo, nunca igual
        return [0, niceMax];
    }

    /** Pinta el control segmentado Color / Escala de grises. */
    function mountModeSelector(container, opts) {
        opts = opts || {};
        var mode = opts.initial || MODES.COLOR;
        if (typeof container === 'string') container = document.getElementById(container);
        if (!container) return { getMode: function () { return mode; } };

        var wrap = document.createElement('div');
        wrap.className = 'chart-theme-selector';
        wrap.style.cssText = 'display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:12px;';

        var label = document.createElement('span');
        label.textContent = 'Visualización:';
        label.style.cssText = 'font-size:12px;color:var(--text-muted,#6b7280);font-weight:600;';
        wrap.appendChild(label);

        // Solo Color y Escala de grises — "Publicación científica" se quitó
        // como opción seleccionable. El modo PUBLICACION sigue existiendo
        // internamente (font/DPI) pero ya no es alcanzable desde este control.
        var options = [
            [MODES.COLOR, 'Color'],
            [MODES.GRISES, 'Escala de grises'],
        ];

        var buttons = {};
        options.forEach(function (opt) {
            var val = opt[0], text = opt[1];
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = text;
            btn.dataset.mode = val;
            btn.style.cssText = 'font-size:12px;padding:4px 10px;border-radius:6px;border:1px solid var(--gris-border,#d1d5db);background:transparent;cursor:pointer;';
            btn.addEventListener('click', function () {
                if (mode === val) return;
                mode = val;
                Object.keys(buttons).forEach(function (k) {
                    var active = k === mode;
                    buttons[k].style.background = active ? 'var(--verde,#1D9E75)' : 'transparent';
                    buttons[k].style.color = active ? '#ffffff' : 'inherit';
                    buttons[k].style.borderColor = active ? 'var(--verde,#1D9E75)' : 'var(--gris-border,#d1d5db)';
                });
                if (typeof opts.onChange === 'function') opts.onChange(mode);
            });
            buttons[val] = btn;
            wrap.appendChild(btn);
        });

        // Estado inicial
        buttons[mode].style.background = 'var(--verde,#1D9E75)';
        buttons[mode].style.color = '#ffffff';
        buttons[mode].style.borderColor = 'var(--verde,#1D9E75)';

        container.appendChild(wrap);
        return { getMode: function () { return mode; } };
    }

    /** Botones de descarga PNG/SVG para una gráfica Plotly, respetando el modo activo. */
    function addPlotlyDownloadButtons(container, opts) {
        opts = opts || {};
        if (typeof container === 'string') container = document.getElementById(container);
        if (!container || typeof Plotly === 'undefined') return;

        var wrap = document.createElement('span');
        wrap.style.cssText = 'display:inline-flex;gap:4px;';

        function makeBtn(label, format) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-outline btn-sm';
            btn.innerHTML = '<i class="ti ti-download"></i> ' + label;
            btn.addEventListener('click', function () {
                var mode = opts.getMode ? opts.getMode() : MODES.COLOR;
                var divEl = typeof opts.divId === 'string' ? document.getElementById(opts.divId) : opts.divId;
                if (!divEl) return;
                var filename = (opts.filenameBase || 'grafico') + '_' + mode;
                var width = divEl.offsetWidth || 900;
                var height = divEl.offsetHeight || 500;

                if (format === 'png') {
                    // Ancho real de impresión (174 mm, doble columna) a 300 DPI —
                    // no un múltiplo arbitrario del tamaño en pantalla. Se aplica
                    // en los 3 modos (Color / Grises / Publicación): la calidad de
                    // exportación exigida por las revistas no depende de la
                    // paleta elegida. `scale` agranda todo el layout (fuente,
                    // líneas, marcadores) de forma proporcional, igual que un
                    // export "2x/3x" — aquí se calcula el factor exacto para
                    // llegar a esa resolución real.
                    var targetPx = Math.round((PUB_WIDTH_MM / 25.4) * PUB_DPI);
                    var scale = targetPx / width;
                    Plotly.toImage(divEl, { format: 'png', width: width, height: height, scale: scale })
                        .then(function (dataUrl) { return fetch(dataUrl); })
                        .then(function (res) { return res.blob(); })
                        .then(function (blob) { return addPngDpi(blob, PUB_DPI); })
                        .then(function (blob) { _downloadBlob(blob, filename + '.png'); })
                        .catch(function (err) { console.error('Descarga PNG:', err); });
                } else {
                    Plotly.downloadImage(divEl, {
                        format: format,
                        filename: filename,
                        width: width,
                        height: height,
                        scale: 2,
                    });
                }
            });
            return btn;
        }

        wrap.appendChild(makeBtn('PNG', 'png'));
        wrap.appendChild(makeBtn('SVG', 'svg'));
        container.appendChild(wrap);
        return wrap;
    }

    /** Descarga PNG de una gráfica Chart.js (canvas no soporta SVG vectorial). */
    function addCanvasDownloadButton(container, opts) {
        opts = opts || {};
        if (typeof container === 'string') container = document.getElementById(container);
        if (!container) return;

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-outline btn-sm';
        btn.innerHTML = '<i class="ti ti-download"></i> PNG';
        btn.addEventListener('click', function () {
            var chart = typeof opts.getChart === 'function' ? opts.getChart() : opts.chart;
            if (!chart) return;
            var mode = opts.getMode ? opts.getMode() : MODES.COLOR;
            var filename = (opts.filenameBase || 'grafico') + '_' + mode + '.png';
            // Misma resolución declarada (300 DPI) en los 3 modos — no solo en
            // "Publicación científica".
            var dataUrl = chart.toBase64Image('image/png', 1);
            fetch(dataUrl)
                .then(function (res) { return res.blob(); })
                .then(function (blob) { return addPngDpi(blob, PUB_DPI); })
                .then(function (blob) { _downloadBlob(blob, filename); })
                .catch(function (err) { console.error('Descarga PNG donut:', err); });
        });
        container.appendChild(btn);
        return btn;
    }

    global.ChartTheme = {
        MODES: MODES,
        PUB_WIDTH_MM: PUB_WIDTH_MM,
        PUB_DPI: PUB_DPI,
        addPngDpi: addPngDpi,
        truncateLabel: truncateLabel,
        extractArray: extractArray,
        shouldShowBarText: shouldShowBarText,
        buildTruncatedTicks: buildTruncatedTicks,
        PALETTE_COLOR: PALETTE_COLOR,
        PALETTE_GRAY: PALETTE_GRAY,
        PATTERNS: PATTERNS,
        MARKER_SYMBOLS: MARKER_SYMBOLS,
        DASH_STYLES: DASH_STYLES,
        isGrayMode: isGrayMode,
        getColor: getColor,
        getPattern: getPattern,
        getSymbol: getSymbol,
        getDash: getDash,
        toGrayscaleHex: toGrayscaleHex,
        taxonLegible: taxonLegible,
        isDarkTheme: isDarkTheme,
        styleTracesByIndex: styleTracesByIndex,
        heatmapColorscale: heatmapColorscale,
        baseLayout: baseLayout,
        yAxisGrid: yAxisGrid,
        computeYRange: computeYRange,
        mountModeSelector: mountModeSelector,
        addPlotlyDownloadButtons: addPlotlyDownloadButtons,
        addCanvasDownloadButton: addCanvasDownloadButton,
        adaptarLayoutMovil: adaptarLayoutMovil,
    };

    // Pantallas angostas (celular). Los layouts se diseñaron para escritorio:
    // leyenda vertical a la derecha, títulos largos en una línea y alturas
    // fijas. En ~375 px eso deja el área de datos aplastada o cortada. Aquí
    // se ajusta SOLO la presentación cuando el contenedor mide menos de
    // ANCHO_MOVIL; en escritorio el layout queda intacto.
    var ANCHO_MOVIL = 576;
    var ALTO_FILA_LEYENDA = 19;
    var ALTO_DATOS_MOVIL = 280;

    function _partirTexto(texto, maxCar) {
        // Respeta los <br> existentes y parte el resto por palabras.
        return String(texto).split(/<br\s*\/?>/i).map(function (linea) {
            var palabras = linea.split(' '), lineas = [], actual = '';
            palabras.forEach(function (p) {
                if (actual && (actual + ' ' + p).replace(/<[^>]+>/g, '').length > maxCar) {
                    lineas.push(actual); actual = p;
                } else {
                    actual = actual ? actual + ' ' + p : p;
                }
            });
            if (actual) lineas.push(actual);
            return lineas.join('<br>');
        }).join('<br>');
    }

    function adaptarLayoutMovil(gd, data, layout) {
        var el = typeof gd === 'string' ? document.getElementById(gd) : gd;
        var ancho = el ? el.clientWidth : 0;
        if (!layout || !ancho || ancho >= ANCHO_MOVIL) return layout;
        data = data || [];

        var L = Object.assign({}, layout);
        var m = Object.assign({ t: 60, b: 60, l: 60, r: 40 }, layout.margin);
        var margenVerticalOriginal = m.t + m.b;

        // Título: más pequeño y en varias líneas para que no se corte.
        var t = L.title, texto = typeof t === 'string' ? t : (t && t.text);
        if (texto) {
            var partido = _partirTexto(texto, Math.max(20, Math.floor(ancho / 8)));
            var lineas = partido.split('<br>').length;
            L.title = Object.assign({}, typeof t === 'object' ? t : {}, {
                text: partido, font: Object.assign({}, (t && t.font) || {}, { size: 12 }),
                x: 0.02, xanchor: 'left',
            });
            m.t = Math.max(m.t, 16 + lineas * 16);
        }

        // Leyenda: horizontal, al pie del gráfico, una entrada por fila
        // (los nombres de taxón son largos). Se suma su alto al del gráfico
        // para que no le quite espacio al área de datos.
        var esPie = data.some(function (tr) { return tr.type === 'pie'; });
        var entradas = esPie ? 0 : data.filter(function (tr) {
            return tr.showlegend !== false && tr.name && tr.type !== 'heatmap';
        }).length;
        if (L.showlegend !== false && entradas > 1) {
            var conTitulo = layout.legend && layout.legend.title && (layout.legend.title.text || typeof layout.legend.title === 'string');
            var altoLeyenda = (entradas + (conTitulo ? 1 : 0)) * ALTO_FILA_LEYENDA + 12;
            L.legend = Object.assign({}, layout.legend, {
                orientation: 'v', x: 0, xanchor: 'left',
                yref: 'container', y: 0, yanchor: 'bottom',
                font: Object.assign({}, (layout.legend && layout.legend.font) || {}, { size: 10 }),
                bgcolor: 'rgba(0,0,0,0)',
            });
            m.b = m.b + altoLeyenda;
            // La leyenda deja de ocupar el margen derecho.
            m.r = Math.min(m.r, 15);
        }

        // Mapas de calor: barra de color más delgada, nombres de taxón
        // recortados con "…" (el nombre completo sigue en el hover) y etiquetas
        // del eje X en vertical para que no se encimen.
        data.forEach(function (tr) {
            if (tr.type === 'heatmap') {
                ['x', 'y'].forEach(function (k) {
                    var eje = k + 'axis', cats = tr[k];
                    if (!Array.isArray(cats) || typeof cats[0] !== 'string') return;
                    var ejeL = Object.assign({}, L[eje] || layout[eje]);
                    if (!ejeL.ticktext) {
                        var t = buildTruncatedTicks(cats, 16);
                        ejeL.tickmode = 'array'; ejeL.tickvals = t.tickvals; ejeL.ticktext = t.ticktext;
                    }
                    if (k === 'x' && cats.length > 4) ejeL.tickangle = -90;
                    L[eje] = ejeL;
                });
                tr.colorbar = Object.assign({}, tr.colorbar, { thickness: 10, tickfont: { size: 9 } });
                if (tr.colorbar.title) {
                    tr.colorbar.title = Object.assign({}, typeof tr.colorbar.title === 'object'
                        ? tr.colorbar.title : { text: tr.colorbar.title }, { font: { size: 9 } });
                }
            }
        });

        // Dispersión (PCoA): las etiquetas de texto junto a cada punto se
        // salen del borde en pantallas angostas; si hay leyenda, el color ya
        // identifica cada muestra y el nombre sigue en el hover.
        if (L.showlegend !== false && entradas > 1) {
            data.forEach(function (tr) {
                if ((tr.type || 'scatter') === 'scatter' && typeof tr.mode === 'string' && tr.mode.indexOf('text') !== -1
                        && tr.mode !== 'text') {
                    tr.mode = tr.mode.split('+').filter(function (p) { return p !== 'text'; }).join('+');
                }
            });
        }

        m.l = Math.min(m.l, 50);
        m.r = Math.min(m.r, 40);
        L.margin = m;
        ['xaxis', 'yaxis'].forEach(function (eje) {
            L[eje] = Object.assign({}, L[eje], { automargin: true });
        });
        L.font = Object.assign({}, layout.font, { size: Math.min((layout.font && layout.font.size) || 12, 11) });
        // Alto: el de escritorio (400-560 px) queda muy alto y angosto en un
        // teléfono, así que el área de datos se limita a ALTO_DATOS_MOVIL y se
        // le suman los márgenes (etiquetas, leyenda y título). Los mapas de calor
        // conservan su alto (crece con el número de taxones). El contenedor
        // suele tener alto fijo en CSS: se ajusta junto con el gráfico. Se
        // guarda el alto original porque al cambiar Color/Grises la gráfica se
        // vuelve a dibujar y no debe crecer en cada redibujo.
        var esHeatmap = data.some(function (tr) { return tr.type === 'heatmap'; });
        if (!esHeatmap) {
            if (!el.dataset.altoBase) el.dataset.altoBase = layout.height || el.clientHeight || 450;
            var areaDatos = Math.max(Number(el.dataset.altoBase) - margenVerticalOriginal, 200);
            L.height = Math.min(areaDatos, ALTO_DATOS_MOVIL) + m.t + m.b;
            el.style.height = L.height + 'px';
        }
        return L;
    }

    // Se aplica a todas las gráficas Plotly de las páginas que cargan este
    // archivo (Plotly siempre se carga justo antes).
    if (global.Plotly && !global.Plotly.__adaptadoMovil) {
        ['newPlot', 'react'].forEach(function (fn) {
            var original = global.Plotly[fn];
            global.Plotly[fn] = function (gd, data, layout, config) {
                if (Array.isArray(data)) layout = adaptarLayoutMovil(gd, data, layout);
                return original.call(this, gd, data, layout, config);
            };
        });
        global.Plotly.__adaptadoMovil = true;
    }
})(window);

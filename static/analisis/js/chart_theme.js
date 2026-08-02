/*
 * ChartTheme — módulo compartido de presentación para las gráficas del
 * módulo de análisis comparativo (Plotly.js y Chart.js).
 *
 * Provee: paletas (color / escala de grises), patrones para diferenciar
 * series sin depender del color, layout base sobrio con cuadrícula de
 * ancho completo, cálculo de rango Y con margen, un selector de modo
 * (Color / Escala de grises) y botones de descarga PNG/SVG que respetan
 * el modo activo.
 *
 * No calcula ni transforma ningún dato científico — solo estilo.
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

    /**
     * Traduce SOLO para mostrar en pantalla el valor de relleno "Unclassified"
     * que el pipeline escribe cuando el laboratorio no identificó ese nivel
     * taxonómico — en inglés tiene sentido para quien ya conoce el pipeline,
     * pero no para un estudiante que lo ve en una leyenda o eje de gráfica.
     * Mismo criterio que el filtro de plantilla `taxon_legible`
     * (analisis/templatetags/custom_filters.py) — no toca el dato real, solo
     * lo que se pinta en el HTML/gráfica.
     */
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

    /** Devuelve '#000000' o '#ffffff', el que mejor contraste con el fondo dado. */
    function contrastTextColor(hex) {
        if (!hex || hex[0] !== '#') return '#000000';
        var h = hex.replace('#', '');
        if (h.length === 3) h = h.split('').map(function (c) { return c + c; }).join('');
        var r = parseInt(h.substr(0, 2), 16), g = parseInt(h.substr(2, 2), 16), b = parseInt(h.substr(4, 2), 16);
        var y = 0.299 * r + 0.587 * g + 0.114 * b;
        return y > 150 ? '#000000' : '#ffffff';
    }

    /**
     * Aplica color + patrón/símbolo por índice de trace. Pensado para
     * gráficas donde cada trace = una categoría/muestra independiente
     * (barras agrupadas o apiladas por muestra/taxón, PCoA un punto por
     * muestra). No tocar cuando el color de cada punto ya tiene un
     * significado propio (ver toGrayscaleHex para esos casos).
     */
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

    /**
     * Colorea por punto una única trace que representa varias categorías
     * (ej. px.bar/px.pie sin color=, donde todas las barras/porciones viven
     * en una sola trace). Asigna un color distinto por punto y, en modo
     * grises, un patrón distinto por barra para no depender solo del color.
     */
    function styleSingleTraceByPoint(trace, mode) {
        var n = (trace.x || trace.labels || trace.values || trace.y || []).length;
        var colors = [];
        for (var i = 0; i < n; i++) colors.push(getColor(mode, i));
        trace.marker = trace.marker || {};
        trace.marker.color = colors;
        if (trace.type === 'bar' && isGrayMode(mode)) {
            var shapes = [];
            for (var j = 0; j < n; j++) shapes.push(getPattern(j));
            trace.marker.pattern = { shape: shapes, fgcolor: '#ffffff', size: 6 };
        } else if (trace.type === 'bar') {
            trace.marker.pattern = undefined;
        }
        return trace;
    }

    /** Colorscale de heatmap según modo. */
    function heatmapColorscale(mode) {
        return isGrayMode(mode) ? 'Greys' : 'Viridis';
    }

    /**
     * Layout base sobrio, con cuadrícula horizontal de ancho completo.
     *
     * En modo "publicacion" se usa Arial/Helvetica (sans-serif) — no Times/Georgia:
     * las principales editoriales científicas (Elsevier, Springer, Nature, PLOS)
     * piden explícitamente una tipografía sans-serif para el texto DENTRO de las
     * figuras, aun cuando el cuerpo del artículo use una serif como Times New Roman.
     * El tamaño se sube un poco respecto a los otros modos porque esta gráfica se
     * exporta pensando en un ancho de impresión real (~174 mm), mucho menor que el
     * ancho en pantalla — sin margen extra, el texto quedaría ilegible una vez
     * reducido a tamaño de columna.
     */
    function baseLayout(mode) {
        var pub = mode === MODES.PUBLICACION;
        return {
            template: 'plotly_white',
            font: {
                family: pub ? 'Arial, Helvetica, sans-serif' : 'Outfit, sans-serif',
                size: pub ? 15 : 12,
                color: pub ? '#000000' : '#374151'
            },
            paper_bgcolor: pub ? '#ffffff' : undefined,
            plot_bgcolor: pub ? '#ffffff' : undefined,
        };
    }

    /**
     * Acorta una etiqueta larga para que quepa en el eje sin solaparse con
     * las demás (mismo comportamiento que Excel: cuando el nombre de una
     * categoría no cabe en el espacio disponible, lo recorta con "…" en vez
     * de dejar que el texto se corte a la mitad o se monte sobre el vecino).
     * El nombre completo se conserva siempre en el dato real — solo cambia
     * lo que se dibuja en el eje (ver hover/leyenda para el nombre íntegro).
     */
    function truncateLabel(text, maxLen) {
        var s = String(text == null ? '' : text);
        maxLen = maxLen || 22;
        return s.length > maxLen ? s.slice(0, maxLen - 1) + '…' : s;
    }

    /**
     * Construye {tickvals, ticktext} para un eje categórico, truncando cada
     * categoría a `maxLen` caracteres. `tickvals` reutiliza las categorías
     * reales (necesario para que Plotly asocie cada texto truncado con su
     * posición correcta en un eje de tipo categoría).
     */
    function buildTruncatedTicks(categorias, maxLen) {
        var vals = Array.from(new Set(categorias));
        return {
            tickvals: vals,
            ticktext: vals.map(function (c) { return truncateLabel(c, maxLen); }),
        };
    }

    /**
     * Con pocas barras el % cabe legible sobre/dentro de cada una y ayuda a
     * leer el dato sin pasar el cursor. Con muchas (Top 25/50 × varias
     * muestras) se amontona en trazos ilegibles — a partir de este umbral
     * de barras totales (categorías × series) se deja de imprimir el texto
     * y el valor exacto queda solo en el hover.
     */
    var DENSE_BAR_THRESHOLD = 32;
    function shouldShowBarText(nCategorias, nSeries) {
        return (nCategorias * (nSeries || 1)) <= DENSE_BAR_THRESHOLD;
    }

    /** Ancho de referencia (doble columna, mm) y DPI mínimo aceptados por la
     * mayoría de revistas científicas (Elsevier/Springer/MDPI/Frontiers). */
    var PUB_WIDTH_MM = 174;
    var PUB_DPI = 300;

    // ---- Utilidades PNG: inyecta el chunk pHYs (resolución real) ----------
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
        return {
            showgrid: true,
            // Gris sólido y opaco — el valor anterior (rgba con 35% de opacidad)
            // quedaba casi invisible sobre el fondo blanco. Sigue siendo sobrio,
            // pero ahora se nota a simple vista sin tener que acercarse a la
            // pantalla.
            gridcolor: '#c8c8c8',
            gridwidth: 1,
            zeroline: false,
        };
    }

    /**
     * Plotly a veces serializa un array numérico de una trace (x/y/z) en un
     * formato binario compacto — {dtype:'f8', bdata:'<base64>'} — en vez de
     * un array JS normal. Si no se decodifica, código que lee `trace.y`
     * directamente (ej. para calcular el rango del eje) no encuentra
     * números y termina sin aplicar ningún margen, aunque la gráfica en sí
     * se vea bien (Plotly SÍ sabe decodificar este formato internamente).
     */
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

    /**
     * Calcula [0, niceMax] redondeando el máximo real hacia arriba, al
     * siguiente múltiplo "limpio" de la cuadrícula (1/2/5 × una potencia de
     * 10) — igual que el autoescalado de Excel: si el valor más alto es 26,
     * la línea de la cuadrícula ya debe estar en 30, no en 26 exacto ni en
     * un valor intermedio arbitrario. Así ninguna barra ni su etiqueta
     * queda pegada o cortada contra el borde del área de la gráfica.
     */
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
        contrastTextColor: contrastTextColor,
        styleTracesByIndex: styleTracesByIndex,
        styleSingleTraceByPoint: styleSingleTraceByPoint,
        heatmapColorscale: heatmapColorscale,
        baseLayout: baseLayout,
        yAxisGrid: yAxisGrid,
        computeYRange: computeYRange,
        mountModeSelector: mountModeSelector,
        addPlotlyDownloadButtons: addPlotlyDownloadButtons,
        addCanvasDownloadButton: addCanvasDownloadButton,
    };
})(window);

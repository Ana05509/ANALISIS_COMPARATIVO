/**
 * Sidebar del admin siempre fijo y visible — pero SOLO en escritorio
 * (>=1024px, mismo umbral que el @media de admin_personalizado.css que
 * fuerza el sidebar visible desde ese ancho). Por debajo de eso, Unfold
 * lo maneja como cajón móvil (oculto + botón de hamburguesa) — este
 * script no debe tocarlo, o queda permanentemente abierto tapando todo
 * el contenido en un celular, sin ninguna forma de cerrarlo.
 * Se carga en <head> antes de Alpine.js.
 */
(function () {

    function esEscritorio() {
        return window.innerWidth >= 1024;
    }

    /* ── 1. Bloquear cierre desde localStorage — solo aplica en escritorio.
       Alpine usa una clave aparte (sidebarMobileOpen) para el cajón móvil,
       pero interceptar setItem de forma incondicional igual competía con
       cualquier lógica que dependiera de sidebarDesktopOpen en pantallas
       chicas — se re-evalúa el ancho en cada llamada, no solo una vez al
       cargar el script, para que responda bien si alguien rota una
       tablet o cambia el tamaño de la ventana. ── */
    if (esEscritorio()) {
        localStorage.setItem('sidebarDesktopOpen', '1');
    }
    var _set = localStorage.setItem.bind(localStorage);
    localStorage.setItem = function (k, v) {
        if (k === 'sidebarDesktopOpen' && esEscritorio()) {
            _set(k, '1');
        } else {
            _set(k, v);
        }
    };

    /* sidebarWidth: Unfold usa 288px por defecto, y ese ancho es el que le
       quita espacio real a las tablas en TODOS los listados del admin — con
       columnas ya angostas, esos 288px eran la diferencia entre que la tabla
       entrara sin scroll horizontal o no, especialmente en laptops. Se fija
       en 220px (el mínimo que Unfold permite, ver nav_sidebar.html) en cada
       carga de página; los ítems del menú ya truncan con "…" así que un
       sidebar angosto no corta ni superpone nada. Quien lo necesite más
       ancho puede seguir arrastrando el borde derecho del sidebar — vuelve
       a 220px en la siguiente página, no queda "roto" para el resto.
       Esto no afecta el cajón móvil (que no usa este ancho), así que se
       deja sin condicionar. */
    localStorage.setItem('sidebarWidth', '220');

    /* ── 2. Aplicar estilos al sidebar (inline > !important de Tailwind) ──
       Solo en escritorio: es la parte que lo vuelve "siempre visible", así
       que en móvil directamente no se ejecuta y Alpine queda a cargo. */
    function fixSidebar() {
        if (!esEscritorio()) return;

        var page = document.getElementById('page');
        if (!page) return;

        /* Alpine wrapper: primer elemento hijo de #page */
        var alpineWrap = page.firstElementChild;
        if (!alpineWrap) return;

        /* Ghost wrapper: primer elemento hijo del Alpine wrapper */
        var ghostWrap = alpineWrap.firstElementChild;
        if (!ghostWrap) return;

        /* Sidebar real */
        var sidebar = document.getElementById('nav-sidebar');

        /* ── Alpine wrapper → sticky en el flex row ── */
        var aw = alpineWrap.style;
        aw.setProperty('position',    'sticky',       'important');
        aw.setProperty('top',         '0',            'important');
        aw.setProperty('height',      '100dvh',       'important');
        aw.setProperty('alignSelf',   'flex-start',   'important');
        aw.setProperty('flexShrink',  '0',            'important');

        /* ── Ghost wrapper → siempre visible y relativo ── */
        var gw = ghostWrap.style;
        gw.setProperty('display',   'block',    'important');
        gw.setProperty('position',  'relative', 'important');
        gw.setProperty('height',    '100dvh',   'important');

        /* ── Sidebar → relativo, altura fija ── */
        /* NO se toca overflow: Unfold ya gestiona el scroll interno del nav.
           Poner overflow-y:auto aquí crea un bloque de clipping que recorta
           el dropdown del usuario (menú pie de sidebar). */
        if (sidebar) {
            var sw = sidebar.style;
            sw.setProperty('position', 'relative', 'important');
            sw.setProperty('top',      'auto',     'important');
            sw.setProperty('bottom',   'auto',     'important');
            sw.setProperty('left',     'auto',     'important');
            sw.setProperty('height',   '100dvh',   'important');
        }

        /* ── Encabezado del sidebar (logo + nombre) → sticky interno ── */
        var inner = document.getElementById('nav-sidebar-inner');
        if (inner) {
            inner.style.setProperty('minHeight', '0', 'important');
            var header = inner.firstElementChild;
            if (header) {
                var hh = header.style;
                hh.setProperty('position',         'sticky',  'important');
                hh.setProperty('top',              '0',       'important');
                hh.setProperty('zIndex',           '20',      'important');
                hh.setProperty('backgroundColor',  'inherit', 'important');
            }
        }

        /* ── Botón dock_to_right (toggle) → ocultarlo en escritorio ── */
        document.querySelectorAll('body *').forEach(function (el) {
            var attr = el.getAttribute('x-on:click') || '';
            if (attr.indexOf('sidebarDesktopOpen') !== -1) {
                /* Ocultar el botón y su contenedor padre */
                var parent = el.closest('span.cursor-pointer') || el.parentElement;
                if (parent) parent.style.setProperty('display', 'none', 'important');
                /* Ocultar el separador a continuación */
                var next = parent ? parent.nextElementSibling : null;
                if (next) next.style.setProperty('display', 'none', 'important');
            }
        });
    }

    /* Deshace los estilos forzados si la ventana cruza a móvil (p. ej. se
       gira una tablet, o se achica la ventana) — sin esto, alguien que
       abre el panel en escritorio y después achica la ventana se queda
       con el sidebar trabado en el estado de escritorio. */
    function restaurarEnMovil() {
        var page = document.getElementById('page');
        if (!page || !page.firstElementChild || !page.firstElementChild.firstElementChild) return;
        var alpineWrap = page.firstElementChild;
        var ghostWrap = alpineWrap.firstElementChild;
        [alpineWrap, ghostWrap, document.getElementById('nav-sidebar')].forEach(function (el) {
            if (el) {
                el.style.removeProperty('position');
                el.style.removeProperty('top');
                el.style.removeProperty('bottom');
                el.style.removeProperty('left');
                el.style.removeProperty('height');
                el.style.removeProperty('align-self');
                el.style.removeProperty('flex-shrink');
                el.style.removeProperty('display');
            }
        });
    }

    var estabaEnEscritorio = esEscritorio();

    /* ── 3. Ejecutar al cargar el DOM ── */
    document.addEventListener('DOMContentLoaded', function () {
        fixSidebar();

        /* Observar si Alpine intenta cambiar clases/estilos del ghost wrapper
           — solo se re-fuerza en escritorio; en móvil se deja que Alpine
           controle el cajón (abrir/cerrar) sin interferencia. */
        var page = document.getElementById('page');
        if (!page || !page.firstElementChild || !page.firstElementChild.firstElementChild) return;
        var ghostWrap = page.firstElementChild.firstElementChild;

        var obs = new MutationObserver(function (mutations) {
            if (!esEscritorio()) return;
            mutations.forEach(function (m) {
                if (m.attributeName === 'class' || m.attributeName === 'style') {
                    /* Re-forzar display:block si Alpine intentó ocultarlo */
                    ghostWrap.style.setProperty('display',  'block',    'important');
                    ghostWrap.style.setProperty('position', 'relative', 'important');
                    ghostWrap.style.setProperty('height',   '100dvh',   'important');
                }
            });
        });
        obs.observe(ghostWrap, { attributes: true, attributeFilter: ['class', 'style'] });

        window.addEventListener('resize', function () {
            var ahoraEscritorio = esEscritorio();
            if (ahoraEscritorio && !estabaEnEscritorio) {
                fixSidebar();
            } else if (!ahoraEscritorio && estabaEnEscritorio) {
                restaurarEnMovil();
            }
            estabaEnEscritorio = ahoraEscritorio;
        });
    });

})();

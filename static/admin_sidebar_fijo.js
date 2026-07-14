/**
 * Sidebar del admin siempre fijo y visible.
 * Se carga en <head> antes de Alpine.js.
 */
(function () {

    /* ── 1. Bloquear cierre desde localStorage ── */
    localStorage.setItem('sidebarDesktopOpen', '1');
    var _set = localStorage.setItem.bind(localStorage);
    localStorage.setItem = function (k, v) {
        _set(k, k === 'sidebarDesktopOpen' ? '1' : v);
    };

    /* ── 2. Aplicar estilos al sidebar (inline > !important de Tailwind) ── */
    function fixSidebar() {
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

    /* ── 3. Ejecutar al cargar el DOM ── */
    document.addEventListener('DOMContentLoaded', function () {
        fixSidebar();

        /* Observar si Alpine intenta cambiar clases/estilos del ghost wrapper */
        var page = document.getElementById('page');
        if (!page || !page.firstElementChild || !page.firstElementChild.firstElementChild) return;
        var ghostWrap = page.firstElementChild.firstElementChild;

        var obs = new MutationObserver(function (mutations) {
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
    });

})();

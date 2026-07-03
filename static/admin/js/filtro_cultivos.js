/**
 * Filtra el <select> de "Variedad / clon" en el admin de Muestras de Suelo
 * para mostrar solo las variedades del cultivo elegido.
 *
 * No usa AJAX: cada <option> de #id_variedad_clon ya trae data-cultivo="<id>"
 * (ver VariedadClonSelect en analisis/admin.py), así que solo se ocultan
 * las opciones que no coinciden con el cultivo seleccionado.
 */
(function () {
    'use strict';

    function filtrarVariedades() {
        var cultivoSelect  = document.getElementById('id_cultivo');
        var variedadSelect = document.getElementById('id_variedad_clon');
        if (!cultivoSelect || !variedadSelect) return;

        var cultivoId = cultivoSelect.value;

        Array.prototype.forEach.call(variedadSelect.options, function (opt) {
            if (!opt.value) {
                opt.hidden = false;
                return;
            }
            opt.hidden = !!cultivoId && opt.getAttribute('data-cultivo') !== cultivoId;
        });

        var actual = variedadSelect.options[variedadSelect.selectedIndex];
        if (cultivoId && actual && actual.value && actual.getAttribute('data-cultivo') !== cultivoId) {
            variedadSelect.value = '';
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var cultivoSelect = document.getElementById('id_cultivo');
        if (!cultivoSelect) return;
        filtrarVariedades();
        cultivoSelect.addEventListener('change', filtrarVariedades);
    });
})();

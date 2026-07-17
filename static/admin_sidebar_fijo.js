/**
 * Sidebar del admin siempre abierto y de ancho angosto fijo.
 *
 * Alpine.js (base de Unfold) ya inicializa sidebarDesktopOpen en `true`
 * cuando localStorage no tiene nada guardado — solo se cierra si queda
 * un '0' de una sesión anterior, o si se hace clic en alguno de los dos
 * botones para colapsarlo (ya ocultos vía CSS en admin_personalizado.css,
 * así que en este panel no hay forma de que eso vuelva a pasar). Este
 * script se limita a limpiar cualquier '0' que haya quedado guardado de
 * antes. Se carga sin defer, antes que Alpine, así que corre a tiempo.
 *
 * sidebarWidth: Unfold usa 288px por defecto, y ese ancho es el que le
 * quita espacio real a las tablas en TODOS los listados del admin — con
 * columnas ya angostas, esos 288px eran la diferencia entre que la tabla
 * entrara sin scroll horizontal o no, especialmente en laptops. Se fija
 * en 220px (el mínimo que Unfold permite, ver nav_sidebar.html) en cada
 * carga de página; los ítems del menú ya truncan con "…" así que un
 * sidebar angosto no corta ni superpone nada. Quien lo necesite más
 * ancho puede seguir arrastrando el borde derecho del sidebar — vuelve
 * a 220px en la siguiente página, no queda "roto" para el resto.
 */
localStorage.setItem('sidebarDesktopOpen', '1');
localStorage.setItem('sidebarWidth', '220');

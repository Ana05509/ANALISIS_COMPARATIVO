import math

from analisis.constants import NIVELES_VALIDOS

FILTROS_EXCLUSION = {"others", "unclassified", "unknown", "nan", "", "others sp"}

class DiversityService:
    """Servicio bioinformático para la evaluación de biodiversidad microbiana."""

    # ---------------------------
    # DIVERSIDAD ALFA (Intra-muestra)
    # ---------------------------

    @staticmethod
    def calcular_riqueza(df):
        """Calcula el número de taxones únicos presentes."""
        if df.empty or "%_hits" not in df.columns:
            return 0
        return len(df[df["%_hits"] > 0])

    @staticmethod
    def _proporciones(df):
        """Convierte columna '%_hits' a proporciones (suma = 1), filtrando ceros."""
        abundancias = df["%_hits"].astype(float)
        abundancias = abundancias[abundancias > 0]
        total = abundancias.sum()
        if total == 0 or abundancias.empty:
            return None
        return abundancias / total

    @staticmethod
    def calcular_shannon(df):
        if df.empty or "%_hits" not in df.columns:
            return 0.0
        p = DiversityService._proporciones(df)
        if p is None:
            return 0.0
        return round(float(-sum(pi * math.log(pi) for pi in p)), 4)

    @staticmethod
    def calcular_simpson(df):
        if df.empty or "%_hits" not in df.columns:
            return 0.0
        p = DiversityService._proporciones(df)
        if p is None:
            return 0.0
        return round(float(1.0 - sum(pi ** 2 for pi in p)), 4)

    @staticmethod
    def calcular_equitatividad(df):
        s = DiversityService.calcular_riqueza(df)
        if s <= 1:
            return 0.0
        p = DiversityService._proporciones(df)
        if p is None:
            return 0.0
        # Usa H' sin redondear para no propagar error de redondeo a J'
        h_exact = -sum(pi * math.log(pi) for pi in p)
        return round(float(h_exact / math.log(s)), 4)

    @staticmethod
    def calcular_diversidad_alfa(df):
        """Consolida el perfil de diversidad alfa (Shannon, Simpson, Pielou, Riqueza)."""
        if df.empty or "%_hits" not in df.columns:
            return {"riqueza": 0, "shannon": 0.0, "simpson": 0.0, "equitatividad": 0.0}
        p = DiversityService._proporciones(df)
        if p is None:
            return {"riqueza": 0, "shannon": 0.0, "simpson": 0.0, "equitatividad": 0.0}
        s = len(p)
        h = abs(-sum(pi * math.log(pi) for pi in p))
        d = 1.0 - sum(pi ** 2 for pi in p)
        j = h / math.log(s) if s > 1 else 0.0
        return {
            "riqueza":       s,
            "shannon":       round(float(h), 4),
            "simpson":       round(float(d), 4),
            "equitatividad": round(float(j), 4),
        }

    # ---------------------------
    # DIVERSIDAD BETA (Inter-muestra)
    # ---------------------------

    @staticmethod
    def _obtener_set_taxonomico_limpio(df, nivel="genus"):
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"
        if df.empty or campo not in df.columns:
            return set()
        taxas_raw = df[campo].dropna().astype(str).str.strip().str.lower()
        return {t for t in taxas_raw if t not in FILTROS_EXCLUSION}

    @staticmethod
    def identificar_compartidos(df_a, df_b, nivel="genus"):
        set_a = DiversityService._obtener_set_taxonomico_limpio(df_a, nivel)
        set_b = DiversityService._obtener_set_taxonomico_limpio(df_b, nivel)
        return sorted(list(set_a & set_b))

    @staticmethod
    def identificar_exclusivos(df_a, df_b, nivel="genus"):
        set_a = DiversityService._obtener_set_taxonomico_limpio(df_a, nivel)
        set_b = DiversityService._obtener_set_taxonomico_limpio(df_b, nivel)
        return {
            "exclusivos_a": sorted(list(set_a - set_b)),
            "exclusivos_b": sorted(list(set_b - set_a)),
        }

    @staticmethod
    def calcular_similitud_jaccard(df_a, df_b, nivel="genus"):
        set_a = DiversityService._obtener_set_taxonomico_limpio(df_a, nivel)
        set_b = DiversityService._obtener_set_taxonomico_limpio(df_b, nivel)
        interseccion = len(set_a & set_b)
        union = len(set_a | set_b)
        return round(float(interseccion / union), 4) if union > 0 else 0.0

    @staticmethod
    def calcular_diversidad_beta(df_a, df_b, nivel="genus"):
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"
        compartidos = DiversityService.identificar_compartidos(df_a, df_b, campo)
        return {
            "compartidos": len(compartidos),
            "compartidos_lista": compartidos,
            "exclusivos": DiversityService.identificar_exclusivos(df_a, df_b, campo),
            "jaccard": DiversityService.calcular_similitud_jaccard(df_a, df_b, campo),
            "total_taxa_reales_a": DiversityService.calcular_riqueza(df_a),
            "total_taxa_reales_b": DiversityService.calcular_riqueza(df_b),
            "nivel_evaluado": campo
        }

    # ---------------------------
    # DIVERSIDAD GAMMA (Meta-comunidad)
    # ---------------------------

    @staticmethod
    def calcular_diversidad_gamma(df_pooled):
        """
        Diversidad gamma: diversidad total de la metacomunidad (unión de todas
        las muestras combinadas). df_pooled debe tener columna '%_hits'.
        """
        alfa = DiversityService.calcular_diversidad_alfa(df_pooled)
        return {
            "riqueza_gamma":      alfa["riqueza"],
            "shannon_gamma":      alfa["shannon"],
            "simpson_gamma":      alfa["simpson"],
            "equitatividad_gamma": alfa["equitatividad"],
        }

    @staticmethod
    def matriz_bray_curtis(matriz_abundancias):
        """
        Matriz n×n de disimilitud Bray-Curtis entre las filas (muestras) de
        `matriz_abundancias` (muestras × taxa). Cada fila se normaliza antes a
        proporciones para que la profundidad de secuenciación no pese en la
        distancia; una fila sin lecturas se deja en cero en lugar de dividir
        entre cero.
        """
        import numpy as np
        from scipy.spatial.distance import pdist, squareform

        matriz = np.asarray(matriz_abundancias, dtype=float)
        sumas = matriz.sum(axis=1, keepdims=True)
        sumas[sumas == 0] = 1
        return squareform(pdist(matriz / sumas, metric="braycurtis"))

    # ---------------------------
    # PCoA (Gower, 1966)
    # ---------------------------

    @staticmethod
    def calcular_pcoa(dist_matrix, n_ejes=2) -> dict:
        """
        Análisis de Coordenadas Principales (PCoA, escalamiento multidimensional
        clásico) según Gower (1966): "Some distance properties of latent root and
        vector methods used in multivariate analysis", Biometrika 53: 325-338.

        Procedimiento
        -------------
        1. A = -½·D²  (cuadrado elemento a elemento de las distancias).
        2. Centrado doble: B = J·A·J, con J = I - (1/n)·11ᵀ.
        3. Descomposición espectral de B (np.linalg.eigh); los valores propios
           se ordenan de mayor a menor.
        4. Coordenadas del eje k = vector propio k · √λk  (solo λk > 0).

        Valores propios negativos
        -------------------------
        Si D es euclidiana, B es semidefinida positiva y todos los λ son ≥ 0.
        Bray-Curtis NO es una métrica euclidiana (ni siquiera cumple siempre la
        desigualdad triangular), por lo que B puede tener valores propios
        negativos: corresponden a "dimensiones imaginarias" que ninguna
        configuración real de puntos puede representar. Se reportan para que el
        usuario juzgue su magnitud (|λmin| / λmax); los porcentajes de variación
        explicada se calculan sobre la suma de los valores propios positivos,
        el mismo criterio que usa scikit-bio.

        Parámetros
        ----------
        dist_matrix : array-like (n×n) cuadrada, simétrica, diagonal cero, n ≥ 3
        n_ejes      : número de ejes a devolver (por defecto 2)

        Retorna
        -------
        dict con:
            coords         : ndarray (n × n_ejes)
            pct_varianza   : lista con el % de variación explicada por eje
            autovalores    : lista de todos los valores propios (descendente)
            n_negativos    : cantidad de valores propios negativos
            ratio_negativo : |λmin| / λmax (0.0 si no hay negativos)
        """
        import numpy as np

        D = np.asarray(dist_matrix, dtype=float)

        if D.ndim != 2 or D.shape[0] != D.shape[1]:
            raise ValueError("La matriz de distancias debe ser cuadrada (n × n).")
        n = D.shape[0]
        if n < 3:
            raise ValueError("La PCoA requiere al menos 3 muestras.")
        if np.isnan(D).any():
            raise ValueError("La matriz de distancias contiene valores NaN.")
        if not np.allclose(D, D.T):
            raise ValueError("La matriz de distancias debe ser simétrica.")
        if not np.allclose(np.diag(D), 0.0):
            raise ValueError("La diagonal de la matriz de distancias debe ser cero.")

        A = -0.5 * D ** 2
        J = np.eye(n) - np.full((n, n), 1.0 / n)
        B = J @ A @ J

        autovalores, autovectores = np.linalg.eigh(B)
        orden = np.argsort(autovalores)[::-1]
        autovalores = autovalores[orden]
        autovectores = autovectores[:, orden]

        lambda_max = float(autovalores[0])
        if lambda_max <= 0:
            raise ValueError(
                "La matriz de distancias no tiene varianza que ordenar "
                "(todas las muestras son idénticas)."
            )
        autovalores[np.abs(autovalores) < 1e-10 * lambda_max] = 0.0

        positivos = np.clip(autovalores, 0.0, None)
        coords = autovectores[:, :n_ejes] * np.sqrt(positivos[:n_ejes])
        pct_varianza = positivos[:n_ejes] / positivos.sum() * 100

        n_negativos = int(np.sum(autovalores < 0))
        ratio_negativo = float(abs(autovalores.min()) / lambda_max) if n_negativos else 0.0

        return {
            "coords":         coords,
            "pct_varianza":   [float(p) for p in pct_varianza],
            "autovalores":    [float(v) for v in autovalores],
            "n_negativos":    n_negativos,
            "ratio_negativo": ratio_negativo,
        }

    # ---------------------------
    # PERMANOVA (Anderson, 2001)
    # ---------------------------

    @staticmethod
    def calcular_permanova(matriz_distancias, grupos, n_permutaciones=499, semilla=42):
        """
        PERMANOVA: prueba si la composición microbiana difiere significativamente
        entre grupos usando una matriz de distancias de Bray-Curtis.

        Parámetros
        ----------
        matriz_distancias : array-like (n×n) de distancias pareadas
        grupos            : lista de etiquetas de grupo (longitud n)
        n_permutaciones   : iteraciones para el p-valor (estándar: 499 ó 999)
        semilla           : semilla aleatoria para reproducibilidad

        Retorna dict con pseudo_F, p_value, R², SS y texto de interpretación.
        """
        import numpy as np

        grupos_arr  = np.array(grupos)
        unicos, cnt = np.unique(grupos_arr, return_counts=True)
        n = len(grupos_arr)
        a = len(unicos)
        conteos = dict(zip(unicos.tolist(), cnt.tolist()))

        if a < 2 or n < 3:
            return None

        # Si cada grupo tiene solo 1 muestra no hay SS_dentro que estimar
        if all(c < 2 for c in conteos.values()):
            return {
                "ejecutado":  False,
                "razon": (
                    "Cada grupo tiene una sola muestra. "
                    "PERMANOVA requiere replicados por grupo para estimar la variación intra-grupo."
                ),
                "grupos":    conteos,
                "n_muestras": n,
            }

        dist_sq = np.asarray(matriz_distancias, dtype=float) ** 2

        def _pseudo_f(d_sq, grp):
            u  = np.unique(grp)
            nt = len(grp)
            at = len(u)
            ss_t = np.sum(d_sq) / (2 * nt)
            ss_w = 0.0
            for g in u:
                mask = grp == g
                ng   = int(np.sum(mask))
                if ng < 2:
                    continue
                sub   = d_sq[np.ix_(mask, mask)]
                ss_w += np.sum(sub) / (2 * ng)
            ss_a  = ss_t - ss_w
            df_a  = at - 1
            df_w  = nt - at
            if df_w <= 0 or ss_w <= 0:
                return None, ss_t, ss_a, ss_w
            return (ss_a / df_a) / (ss_w / df_w), ss_t, ss_a, ss_w

        f_obs, ss_t, ss_a, ss_w = _pseudo_f(dist_sq, grupos_arr)
        if f_obs is None:
            return None

        r2 = float(ss_a / ss_t) if ss_t > 0 else 0.0

        rng   = np.random.default_rng(semilla)
        n_geq = 0
        for _ in range(n_permutaciones):
            f_p, *_ = _pseudo_f(dist_sq, rng.permutation(grupos_arr))
            if f_p is not None and f_p >= f_obs:
                n_geq += 1

        p_value      = (n_geq + 1) / (n_permutaciones + 1)
        significativo = p_value < 0.05

        n_reparticiones = DiversityService._contar_reparticiones(list(conteos.values()))
        potencia_limitada = n_reparticiones < 20

        interpretacion = (
            f"Diferencias significativas entre grupos (p = {p_value:.4f} < 0.05). "
            f"El {round(r2*100, 1)}% de la variación total es explicada por los grupos "
            f"(R² = {round(r2, 4)}, pseudo-F = {round(float(f_obs), 4)})."
        ) if significativo else (
            f"No se detectaron diferencias significativas entre grupos (p = {p_value:.4f} ≥ 0.05). "
            f"Los grupos explican el {round(r2*100, 1)}% de la variación total "
            f"(R² = {round(r2, 4)}, pseudo-F = {round(float(f_obs), 4)})."
        )
        if potencia_limitada:
            interpretacion += (
                f" Con {n} muestras solo existen {n_reparticiones} reparticiones distintas; "
                f"el p mínimo alcanzable es ≈ 1/{n_reparticiones}, por lo que la prueba no "
                "puede detectar diferencias significativas con este tamaño muestral."
            )

        return {
            "ejecutado":        True,
            "pseudo_f":         round(float(f_obs), 4),
            "p_value":          round(float(p_value), 4),
            "r2":               round(r2, 4),
            "r2_pct":           round(r2 * 100, 1),
            "ss_entre":         round(float(ss_a), 4),
            "ss_dentro":        round(float(ss_w), 4),
            "ss_total":         round(float(ss_t), 4),
            "n_grupos":         int(a),
            "n_muestras":       int(n),
            "n_permutaciones":  n_permutaciones,
            "significativo":    significativo,
            "grupos":           conteos,
            "n_reparticiones":  n_reparticiones,
            "potencia_limitada": potencia_limitada,
            "interpretacion":   interpretacion,
        }

    @staticmethod
    def _contar_reparticiones(tamanos):
        """
        Número de formas distintas de repartir las muestras en grupos con los
        tamaños dados: coeficiente multinomial n! / ∏ nᵢ!, dividido entre k!
        por cada conjunto de k grupos del mismo tamaño (intercambiar dos
        grupos de igual tamaño produce la misma repartición).
        """
        from collections import Counter

        total = math.factorial(sum(tamanos))
        for t in tamanos:
            total //= math.factorial(t)
        for repeticiones in Counter(tamanos).values():
            total //= math.factorial(repeticiones)
        return total

    # ---------------------------
    # PERMDISP (Anderson, 2006)
    # ---------------------------

    @staticmethod
    def calcular_permdisp(dist_matrix, grupos, n_permutaciones=499, semilla=42):
        """
        PERMDISP (Anderson, 2006, Biometrics 62: 245-253): prueba de
        homogeneidad de las dispersiones multivariadas entre grupos.

        PERMANOVA puede dar p < 0.05 tanto si los grupos difieren en su
        composición media (centroide) como si solo difieren en su variabilidad
        (dispersión). PERMDISP aísla la segunda posibilidad:

        1. PCoA de la matriz de distancias (todos los ejes con λ > 0).
        2. Distancia euclidiana de cada muestra al centroide de su grupo en
           ese espacio.
        3. F de ANOVA de una vía sobre esas distancias.
        4. p por permutación de las etiquetas de grupo sobre las distancias.

        Simplificación: se descartan los ejes de valores propios negativos
        (vegan::betadisper los resta como componente imaginaria). Con
        Bray-Curtis su peso suele ser pequeño — ver `ratio_negativo` de la PCoA.

        Los grupos de una sola muestra se excluyen de la ANOVA: su distancia al
        propio centroide es 0 por construcción y no estima ninguna dispersión,
        así que incluirlos inflaría F. Sí participan en la PCoA.

        Retorna None si no es calculable (menos de 2 grupos con ≥ 2 muestras,
        o sin variación en las distancias).
        """
        import numpy as np

        grupos_todos = np.array(grupos)
        unicos, conteos = np.unique(grupos_todos, return_counts=True)
        unicos = unicos[conteos >= 2]
        if len(unicos) < 2:
            return None

        try:
            coords = DiversityService.calcular_pcoa(dist_matrix, n_ejes=len(grupos_todos))["coords"]
        except ValueError:
            return None

        incluidas = np.isin(grupos_todos, unicos)
        coords = coords[incluidas]
        grupos_arr = grupos_todos[incluidas]
        n = len(grupos_arr)
        a = len(unicos)

        distancias = np.zeros(n)
        for g in unicos:
            mask = grupos_arr == g
            centroide = coords[mask].mean(axis=0)
            distancias[mask] = np.linalg.norm(coords[mask] - centroide, axis=1)

        def _f_anova(z, grp):
            media_global = z.mean()
            ss_entre = 0.0
            ss_dentro = 0.0
            for g in unicos:
                zg = z[grp == g]
                ss_entre += len(zg) * (zg.mean() - media_global) ** 2
                ss_dentro += np.sum((zg - zg.mean()) ** 2)
            if ss_dentro <= 0:
                return None
            return (ss_entre / (a - 1)) / (ss_dentro / (n - a))

        f_obs = _f_anova(distancias, grupos_arr)
        if f_obs is None:
            return None

        rng = np.random.default_rng(semilla)
        n_geq = 0
        for _ in range(n_permutaciones):
            f_p = _f_anova(distancias, rng.permutation(grupos_arr))
            if f_p is not None and f_p >= f_obs:
                n_geq += 1
        p_value = (n_geq + 1) / (n_permutaciones + 1)

        return {
            "f":                round(float(f_obs), 4),
            "p_value":          round(float(p_value), 4),
            "significativo":    p_value < 0.05,
            "n_permutaciones":  n_permutaciones,
            "dispersion_por_grupo": {
                str(g): round(float(distancias[grupos_arr == g].mean()), 4) for g in unicos
            },
        }
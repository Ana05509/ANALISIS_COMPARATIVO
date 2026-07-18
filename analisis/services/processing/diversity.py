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
            "interpretacion": (
                f"Diferencias significativas entre grupos (p = {p_value:.4f} < 0.05). "
                f"El {round(r2*100, 1)}% de la variación total es explicada por los grupos "
                f"(R² = {round(r2, 4)}, pseudo-F = {round(float(f_obs), 4)})."
            ) if significativo else (
                f"No se detectaron diferencias significativas entre grupos (p = {p_value:.4f} ≥ 0.05). "
                f"Los grupos explican el {round(r2*100, 1)}% de la variación total "
                f"(R² = {round(r2, 4)}, pseudo-F = {round(float(f_obs), 4)})."
            ),
        }
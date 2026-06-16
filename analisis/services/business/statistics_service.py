# services/business/statistics_service.py
# Motor de análisis estadístico avanzado para biodiversidad microbiana y metagenómica de suelos.

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import linkage
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import warnings

warnings.filterwarnings('ignore')


class StatisticsService:
    """Análisis estadístico avanzado y blindado de perfiles microbianos y ecología de suelos."""

    @staticmethod
    def calcular_descriptivas(df, columna="%_hits"):
        """
        Calcula estadísticas descriptivas robustas de abundancia microbiana.
        Protegido contra sets vacíos o faltantes.
        """
        if df.empty or columna not in df.columns:
            return None

        datos = df[columna].dropna()
        if len(datos) == 0:
            return None

        media = float(datos.mean())
        std_dev = float(datos.std()) if len(datos) > 1 else 0.0
        variance = float(datos.var()) if len(datos) > 1 else 0.0

        return {
            "media": media,
            "mediana": float(datos.median()),
            "desv_estandar": std_dev,
            "varianza": variance,
            "Q1": float(datos.quantile(0.25)),
            "Q3": float(datos.quantile(0.75)),
            "minimo": float(datos.min()),
            "maximo": float(datos.max()),
            "rango_intercuartil": float(datos.quantile(0.75) - datos.quantile(0.25)),
            "asimetria": float(stats.skew(datos)) if len(datos) > 2 else 0.0,
            "curtosis": float(stats.kurtosis(datos)) if len(datos) > 2 else 0.0,
            "coef_variacion": float((std_dev / media * 100)) if media != 0 else 0.0,
        }

    @staticmethod
    def test_t_independiente(grupo_a, grupo_b, columna="%_hits"):
        """
        Realiza test t de Student para muestras independientes con corrección de Welch.
        Corregido usando acceso a atributos nominales para máxima compatibilidad con Pylance.
        """
        if grupo_a.empty or grupo_b.empty or columna not in grupo_a.columns or columna not in grupo_b.columns:
            return None

        datos_a = grupo_a[columna].dropna().to_numpy(dtype=float)
        datos_b = grupo_b[columna].dropna().to_numpy(dtype=float)
        
        if len(datos_a) < 2 or len(datos_b) < 2:
            return {"error": "Muestras insuficientes en uno de los grupos (mínimo 2 observaciones)."}

        if np.var(datos_a) == 0 and np.var(datos_b) == 0:
            return {
                "t_statistic": 0.0,
                "p_value": 1.0,
                "significante": False,
                "media_a": float(np.mean(datos_a)),
                "media_b": float(np.mean(datos_b)),
                "diferencia_medias": 0.0,
                "df": int(len(datos_a) + len(datos_b) - 2)
            }

        # Acceder a las propiedades nominales (.statistic y .pvalue) resuelve la ambigüedad del objeto tuple
        resultado_test = stats.ttest_ind(datos_a, datos_b, equal_var=False)
        
        t_stat = float(getattr(resultado_test, 'statistic', 0.0))
        p_val_raw = float(getattr(resultado_test, 'pvalue', 1.0))
        
        if np.isnan(t_stat) or np.isnan(p_val_raw):
            return {"error": "No se pudo calcular el estadístico debido a colinealidad extrema."}

        return {
            "t_statistic": t_stat,
            "p_value": p_val_raw,
            "significante": bool(p_val_raw < 0.05),
            "media_a": float(np.mean(datos_a)),
            "media_b": float(np.mean(datos_b)),
            "diferencia_medias": float(np.mean(datos_a) - np.mean(datos_b)),
            "df": int(len(datos_a) + len(datos_b) - 2),
        }

    @staticmethod
    def test_mann_whitney(grupo_a, grupo_b, columna="%_hits"):
        """
        Realiza el test no paramétrico de Mann-Whitney U con tipado seguro.
        """
        if grupo_a.empty or grupo_b.empty or columna not in grupo_a.columns or columna not in grupo_b.columns:
            return None

        datos_a = grupo_a[columna].dropna().to_numpy(dtype=float)
        datos_b = grupo_b[columna].dropna().to_numpy(dtype=float)
        
        if len(datos_a) == 0 or len(datos_b) == 0:
            return None

        try:
            resultado_mw = stats.mannwhitneyu(datos_a, datos_b, alternative="two-sided")
            u_stat = float(getattr(resultado_mw, 'statistic', 0.0))
            p_val = float(getattr(resultado_mw, 'pvalue', 1.0))
            
            return {
                "u_statistic": u_stat,
                "p_value": p_val,
                "significante": bool(p_val < 0.05),
                "mediana_a": float(np.median(datos_a)),
                "mediana_b": float(np.median(datos_b)),
                "diferencia_medianas": float(np.median(datos_a) - np.median(datos_b)),
            }
        except Exception as e:
            return {"error": f"Fallo en ejecución de Mann-Whitney: {str(e)}"}

    @staticmethod
    def test_anova(*grupos, columna="%_hits"):
        """Realiza ANOVA de una vía blindado contra grupos homogéneos sin varianza."""
        if not grupos or columna not in grupos[0].columns:
            return None

        datos_grupos = [g[columna].dropna().to_numpy(dtype=float) for g in grupos if not g.empty]
        datos_grupos = [d for d in datos_grupos if len(d) > 0]
        
        if len(datos_grupos) < 2:
            return None

        todos_datos = np.concatenate(datos_grupos)
        if np.var(todos_datos) == 0:
            return {
                "f_statistic": 0.0,
                "p_value": 1.0,
                "significante": False,
                "grupos": len(datos_grupos),
                "observaciones": len(todos_datos),
            }

        try:
            resultado_anova = stats.f_oneway(*datos_grupos)
            f_stat = float(getattr(resultado_anova, 'statistic', 0.0))
            p_val = float(getattr(resultado_anova, 'pvalue', 1.0))
            
            return {
                "f_statistic": f_stat if not np.isnan(f_stat) else 0.0,
                "p_value": p_val if not np.isnan(p_val) else 1.0,
                "significante": bool(p_val < 0.05) if not np.isnan(p_val) else False,
                "grupos": len(datos_grupos),
                "observaciones": len(todos_datos),
            }
        except Exception as e:
            return {"error": f"Error en cálculo de varianza ANOVA: {str(e)}"}

    @staticmethod
    def calcular_pca(df, n_componentes=2, columnas_excluir=None):
        """
        Calcula PCA aislando de forma estricta las columnas categóricas o funcionales.
        """
        if df.empty:
            return None

        if columnas_excluir is None:
            columnas_excluir = []
        
        cols_numericas = df.select_dtypes(include=[np.number]).columns
        cols_uso = [c for c in cols_numericas if c not in columnas_excluir]
        
        X = df[cols_uso].fillna(0.0)
        
        if X.empty or X.shape[0] < 2:
            return {"error": "Filas/observaciones insuficientes para proyectar Componentes Principales."}

        varianzas = X.var(axis=0)
        cols_validas = varianzas[varianzas > 0].index.tolist()
        
        if len(cols_validas) == 0:
            return {"error": "Varianza idéntica a cero en todas las dimensiones del set biológico."}
            
        X_filtrado = X[cols_validas]

        try:
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_filtrado)
            
            comp_reales = min(n_componentes, X_scaled.shape[0], X_scaled.shape[1])
            pca = PCA(n_components=comp_reales)
            X_pca = pca.fit_transform(X_scaled)
            
            return {
                "componentes": X_pca.tolist(),
                "varianza_explicada": pca.explained_variance_ratio_.tolist(),
                "varianza_acumulada": np.cumsum(pca.explained_variance_ratio_).tolist(),
                "loadings": pca.components_.tolist(),
                "n_componentes": int(pca.n_components_),
                "total_varianza": float(sum(pca.explained_variance_ratio_)),
            }
        except Exception as e:
            return {"error": f"Fallo algebraico en la descomposición del espacio PCA: {str(e)}"}

    @staticmethod
    def calcular_clustering_kmeans(df, n_clusters=3, columnas_excluir=None):
        """Ejecuta particionamiento por K-Means idóneo para matrices consolidadas transpuertas."""
        if df.empty:
            return None

        if columnas_excluir is None:
            columnas_excluir = []
        
        cols_numericas = df.select_dtypes(include=[np.number]).columns
        cols_uso = [c for c in cols_numericas if c not in columnas_excluir]
        
        X = df[cols_uso].fillna(0.0)
        
        n_muestras = X.shape[0]
        if n_muestras < 2:
            return {"error": "Observaciones insuficientes para entrenar centroides de clustering."}

        clusters_reales = max(2, min(int(n_clusters), n_muestras - 1)) if n_muestras > 2 else 1
        
        if clusters_reales == 1:
            return {
                "labels": [0] * n_muestras,
                "centros": [],
                "inercia": 0.0,
                "n_clusters": 1,
                "iteraciones": 0
            }

        try:
            varianzas = X.var(axis=0)
            cols_validas = varianzas[varianzas > 0].index.tolist()
            X_input = X[cols_validas] if cols_validas else X

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_input)
            
            kmeans = KMeans(n_clusters=clusters_reales, random_state=42, n_init='auto')
            labels = kmeans.fit_predict(X_scaled)
            
            return {
                "labels": labels.tolist(),
                "centros": kmeans.cluster_centers_.tolist(),
                "inercia": float(kmeans.inertia_),
                "n_clusters": clusters_reales,
                "iteraciones": int(kmeans.n_iter_ or 0),
            }
        except Exception as e:
            return {"error": f"Error en el algoritmo de partición K-Means: {str(e)}"}

    @staticmethod
    def calcular_dendrograma_datos(df, columnas_excluir=None, metodo="ward"):
        """Prepara la matriz de ligamiento para el árbol jerárquico de similitud de suelos."""
        if df.empty:
            return None

        if columnas_excluir is None:
            columnas_excluir = []
        
        cols_numericas = df.select_dtypes(include=[np.number]).columns
        cols_uso = [c for c in cols_numericas if c not in columnas_excluir]
        
        X = df[cols_uso].fillna(0.0)
        if X.empty or X.shape[0] < 2:
            return None

        try:
            varianzas = X.var(axis=0)
            cols_validas = varianzas[varianzas > 0].index.tolist()
            X_input = X[cols_validas] if cols_validas else X

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_input)
            
            Z = linkage(X_scaled, method=metodo)
            return {
                "linkage_matrix": Z.tolist(),
                "metodo": metodo,
                "n_observaciones": int(X_scaled.shape[0]),
                "n_caracteristicas": int(X_scaled.shape[1]),
            }
        except Exception as e:
            return {"error": f"Incapacidad de resolver ligamiento jerárquico: {str(e)}"}

    @staticmethod
    def calcular_similitud_jaccard(conjunto_a, conjunto_b):
        """Calcula el índice de Jaccard clásico basado en presencia/ausencia de microorganismos."""
        set_a = set(conjunto_a) if not isinstance(conjunto_a, set) else conjunto_a
        set_b = set(conjunto_b) if not isinstance(conjunto_b, set) else conjunto_b
        
        if len(set_a) == 0 and len(set_b) == 0:
            return 1.0
        
        interseccion = len(set_a & set_b)
        union = len(set_a | set_b)
        
        return float(interseccion / union) if union > 0 else 0.0

    @staticmethod
    def calcular_similitud_braycurtis(df_a, df_b, columna_taxo="Genus", columna_abundancia="%_hits"):
        """
        Calcula el índice ecológico real de Bray-Curtis (Alineado por Taxonomía).
        """
        if df_a.empty or df_b.empty or columna_abundancia not in df_a.columns or columna_taxo not in df_a.columns:
            return None

        serie_a = df_a.groupby(columna_taxo)[columna_abundancia].sum()
        serie_b = df_b.groupby(columna_taxo)[columna_abundancia].sum()

        all_taxa = serie_a.index.union(serie_b.index)
        vector_a = serie_a.reindex(all_taxa, fill_value=0.0).to_numpy()
        vector_b = serie_b.reindex(all_taxa, fill_value=0.0).to_numpy()

        sum_abs_diff = np.sum(np.abs(vector_a - vector_b))
        sum_total = np.sum(vector_a + vector_b)

        if sum_total == 0:
            return 0.0

        distancia = sum_abs_diff / sum_total
        return float(distancia) if not np.isnan(distancia) else 0.0

    @staticmethod
    def test_normalidad_shapiro(df, columna="%_hits"):
        """
        Test de Shapiro-Wilk para evaluación de normalidad con extracción segura.
        """
        if df.empty or columna not in df.columns:
            return None

        datos = df[columna].dropna().to_numpy(dtype=float)
        n = len(datos)
        
        if n < 3 or n > 5000:
            return {
                "error": f"Tamaño muestral fuera de rango para Shapiro-Wilk (N={n}). Requiere entre 3 y 5000 observaciones."
            }

        if np.all(datos == datos[0]):
            return {
                "w_statistic": 1.0,
                "p_value": 1.0,
                "es_normal": True,
                "observaciones": n,
                "nota": "Distribución uniforme constante (Varianza Cero)"
            }

        try:
            resultado_shapiro = stats.shapiro(datos)
            w_stat = float(getattr(resultado_shapiro, 'statistic', resultado_shapiro[0]))
            p_value = float(getattr(resultado_shapiro, 'pvalue', resultado_shapiro[1]))
            
            return {
                "w_statistic": w_stat,
                "p_value": p_value,
                "es_normal": bool(p_value > 0.05),
                "observaciones": n,
            }
        except Exception as e:
            return {"error": f"Fallo al computar Shapiro-Wilk: {str(e)}"}

    @staticmethod
    def generar_reporte_estadistico(df, nivel="Genus", top_n=10):
        """
        Genera el reporte analítico global del suelo sin sesgar métricas científicas.
        """
        if df.empty:
            return None

        descriptivas_completas = StatisticsService.calcular_descriptivas(df, columna="%_hits")
        test_normalidad_completo = StatisticsService.test_normalidad_shapiro(df, columna="%_hits")
        
        top_df = df.nlargest(top_n, "%_hits")
        
        return {
            "descriptivas": descriptivas_completas,
            "normalidad": test_normalidad_completo,
            "taxa_analizados": len(df),
            "nivel": nivel,
            "top_n_solicitado": top_n,
            "dominancia_top_acumulada": float(top_df["%_hits"].sum()) if "%_hits" in top_df.columns else 0.0
        }
    
    @staticmethod
    def calcular_indices_diversidad(df: pd.DataFrame, columna_taxo="Genus", columna_abundancia="%_hits") -> dict:
        """
        Método puente para calcular índices de diversidad alfa (CORREGIDO E INDENTADO).
        Requerido por analysis.py y dashboard.py.
        """
        if df.empty or columna_abundancia not in df.columns:
            return {}
        
        from analisis.services.processing.diversity import DiversityService
        
        # Validación defensiva en caso de que la columna cambie de nombre
        col_real = columna_taxo if columna_taxo in df.columns else df.columns[0]
        
        # Agrupar por taxonomía para evitar duplicados y calcular
        df_agrupado = df.groupby(col_real, as_index=False)[columna_abundancia].sum()
        resultado = DiversityService.calcular_diversidad_alfa(df_agrupado)
        
        return resultado if resultado else {}


# =====================================================================
# ALIAS DE COMPATIBILIDAD: Resuelve el puente con las vistas de Django
# =====================================================================
StatisticalAnalyzer = StatisticsService
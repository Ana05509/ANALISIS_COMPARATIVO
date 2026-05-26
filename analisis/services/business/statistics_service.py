# services/business/statistics_service.py
# Módulo de análisis estadístico avanzado
# README: "Análisis Comparativo: estadística para biodiversidad microbiana"

import pandas as pd
import numpy as np
from scipy import stats
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import pdist, squareform
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import warnings

warnings.filterwarnings('ignore')


class StatisticalAnalyzer:
    """Análisis estadístico avanzado de perfiles microbianos."""

    @staticmethod
    def calcular_descriptivas(df, columna="%_hits"):
        """
        Calcula estadísticas descriptivas de abundancia.
        
        Args:
            df: DataFrame con datos microbianos
            columna: Columna a analizar (default: "%_hits")
        
        Returns:
            dict con mean, std, median, Q1, Q3, min, max, skew, kurtosis
        """
        if df.empty or columna not in df.columns:
            return None

        datos = df[columna].dropna()
        
        return {
            "media": float(datos.mean()),
            "mediana": float(datos.median()),
            "desv_estandar": float(datos.std()),
            "varianza": float(datos.var()),
            "Q1": float(datos.quantile(0.25)),
            "Q3": float(datos.quantile(0.75)),
            "minimo": float(datos.min()),
            "maximo": float(datos.max()),
            "rango_intercuartil": float(datos.quantile(0.75) - datos.quantile(0.25)),
            "asimetria": float(stats.skew(datos)),
            "curtosis": float(stats.kurtosis(datos)),
            "coef_variacion": float((datos.std() / datos.mean() * 100)) if datos.mean() != 0 else 0,
        }

    @staticmethod
    def test_t_independiente(grupo_a, grupo_b, columna="%_hits"):
        """
        Realiza test t de Student para dos muestras independientes.
        
        Args:
            grupo_a, grupo_b: DataFrames de dos grupos
            columna: Columna a analizar
        
        Returns:
            dict con t-statistic, p-value, conclusión
        """
        if grupo_a.empty or grupo_b.empty or columna not in grupo_a.columns:
            return None

        datos_a = grupo_a[columna].dropna()
        datos_b = grupo_b[columna].dropna()
        
        t_stat, p_value = stats.ttest_ind(datos_a, datos_b)
        
        return {
            "t_statistic": float(t_stat),
            "p_value": float(p_value),
            "significante": p_value < 0.05,
            "media_a": float(datos_a.mean()),
            "media_b": float(datos_b.mean()),
            "diferencia_medias": float(datos_a.mean() - datos_b.mean()),
            "df": len(datos_a) + len(datos_b) - 2,
        }

    @staticmethod
    def test_mann_whitney(grupo_a, grupo_b, columna="%_hits"):
        """
        Realiza test de Mann-Whitney U (no-paramétrico).
        Alternativa a t-test cuando datos no son normales.
        """
        if grupo_a.empty or grupo_b.empty or columna not in grupo_a.columns:
            return None

        datos_a = grupo_a[columna].dropna()
        datos_b = grupo_b[columna].dropna()
        
        u_stat, p_value = stats.mannwhitneyu(datos_a, datos_b, alternative="two-sided")
        
        return {
            "u_statistic": float(u_stat),
            "p_value": float(p_value),
            "significante": p_value < 0.05,
            "mediana_a": float(datos_a.median()),
            "mediana_b": float(datos_b.median()),
            "diferencia_medianas": float(datos_a.median() - datos_b.median()),
        }

    @staticmethod
    def test_anova(*grupos, columna="%_hits"):
        """
        Realiza ANOVA de una vía para múltiples grupos.
        
        Args:
            *grupos: DataFrames de múltiples grupos
            columna: Columna a analizar
        
        Returns:
            dict con F-statistic, p-value
        """
        if not grupos or columna not in grupos[0].columns:
            return None

        datos_grupos = [g[columna].dropna().values for g in grupos if not g.empty]
        
        if len(datos_grupos) < 2:
            return None

        f_stat, p_value = stats.f_oneway(*datos_grupos)
        
        return {
            "f_statistic": float(f_stat),
            "p_value": float(p_value),
            "significante": p_value < 0.05,
            "grupos": len(datos_grupos),
            "observaciones": sum(len(g) for g in datos_grupos),
        }

    @staticmethod
    def calcular_pca(df, n_componentes=2, columnas_excluir=None):
        """
        Calcula PCA (Análisis de Componentes Principales).
        
        Args:
            df: DataFrame con datos
            n_componentes: Número de componentes a extraer
            columnas_excluir: Columnas a excluir del análisis (ej: ['taxonomia'])
        
        Returns:
            dict con transformed data, varianza explicada, loadings
        """
        if df.empty:
            return None

        # Preparar datos
        if columnas_excluir is None:
            columnas_excluir = []
        
        cols_numericas = df.select_dtypes(include=[np.number]).columns
        cols_uso = [c for c in cols_numericas if c not in columnas_excluir]
        
        X = df[cols_uso].fillna(0)
        
        if X.empty or X.shape[0] < 2:
            return None

        # Estandarizar
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # PCA
        pca = PCA(n_components=min(n_componentes, X_scaled.shape[1]))
        X_pca = pca.fit_transform(X_scaled)
        
        return {
            "componentes": X_pca.tolist(),
            "varianza_explicada": pca.explained_variance_ratio_.tolist(),
            "varianza_acumulada": np.cumsum(pca.explained_variance_ratio_).tolist(),
            "loadings": pca.components_.tolist(),
            "n_componentes": pca.n_components_,
            "total_varianza": float(sum(pca.explained_variance_ratio_)),
        }

    @staticmethod
    def calcular_clustering_kmeans(df, n_clusters=3, columnas_excluir=None):
        """
        Realiza clustering K-Means.
        
        Args:
            df: DataFrame con datos
            n_clusters: Número de clusters
            columnas_excluir: Columnas a excluir
        
        Returns:
            dict con labels, centros, inercia
        """
        if df.empty:
            return None

        if columnas_excluir is None:
            columnas_excluir = []
        
        cols_numericas = df.select_dtypes(include=[np.number]).columns
        cols_uso = [c for c in cols_numericas if c not in columnas_excluir]
        
        X = df[cols_uso].fillna(0)
        
        if X.empty or X.shape[0] < n_clusters:
            return None

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X_scaled)
        
        return {
            "labels": labels.tolist(),
            "centros": kmeans.cluster_centers_.tolist(),
            "inercia": float(kmeans.inertia_),
            "n_clusters": n_clusters,
            "iteraciones": kmeans.n_iter_,
        }

    @staticmethod
    def calcular_dendrograma_datos(df, columnas_excluir=None, metodo="ward"):
        """
        Prepara datos para dendrograma (clustering jerárquico).
        
        Args:
            df: DataFrame con datos
            columnas_excluir: Columnas a excluir
            metodo: "ward", "complete", "average", "single"
        
        Returns:
            dict con datos para ploteo
        """
        if df.empty:
            return None

        if columnas_excluir is None:
            columnas_excluir = []
        
        cols_numericas = df.select_dtypes(include=[np.number]).columns
        cols_uso = [c for c in cols_numericas if c not in columnas_excluir]
        
        X = df[cols_uso].fillna(0)
        
        if X.empty or X.shape[0] < 2:
            return None

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Calcular matriz de distancias
        Z = linkage(X_scaled, method=metodo)
        
        return {
            "linkage_matrix": Z.tolist(),
            "metodo": metodo,
            "n_observaciones": X_scaled.shape[0],
            "n_caracteristicas": X_scaled.shape[1],
        }

    @staticmethod
    def calcular_similitud_jaccard(conjunto_a, conjunto_b):
        """
        Calcula índice de Jaccard entre dos conjuntos.
        
        Args:
            conjunto_a, conjunto_b: Conjuntos (listas, sets)
        
        Returns:
            float: Índice Jaccard (0 a 1)
        """
        set_a = set(conjunto_a) if not isinstance(conjunto_a, set) else conjunto_a
        set_b = set(conjunto_b) if not isinstance(conjunto_b, set) else conjunto_b
        
        if len(set_a) == 0 and len(set_b) == 0:
            return 1.0
        
        interseccion = len(set_a & set_b)
        union = len(set_a | set_b)
        
        return float(interseccion / union) if union > 0 else 0.0

    @staticmethod
    def calcular_similitud_braycurtis(df_a, df_b, columna="%_hits"):
        """
        Calcula distancia de Bray-Curtis entre dos muestras.
        
        Args:
            df_a, df_b: DataFrames de dos muestras
            columna: Columna de abundancia
        
        Returns:
            float: Distancia Bray-Curtis (0 a 1)
        """
        if df_a.empty or df_b.empty or columna not in df_a.columns:
            return None

        datos_a = df_a[columna].fillna(0).values
        datos_b = df_b[columna].fillna(0).values
        
        # Alinear longitudes
        max_len = max(len(datos_a), len(datos_b))
        datos_a = np.pad(datos_a, (0, max_len - len(datos_a)), mode='constant')
        datos_b = np.pad(datos_b, (0, max_len - len(datos_b)), mode='constant')
        
        distancia = np.sum(np.abs(datos_a - datos_b)) / np.sum(datos_a + datos_b)
        
        return float(distancia) if not np.isnan(distancia) else 0.0

    @staticmethod
    def test_normalidad_shapiro(df, columna="%_hits"):
        """
        Test de Shapiro-Wilk para normalidad.
        
        Args:
            df: DataFrame
            columna: Columna a testear
        
        Returns:
            dict con W-statistic, p-value
        """
        if df.empty or columna not in df.columns:
            return None

        datos = df[columna].dropna()
        
        if len(datos) < 3 or len(datos) > 5000:
            return None

        w_stat, p_value = stats.shapiro(datos)
        
        return {
            "w_statistic": float(w_stat),
            "p_value": float(p_value),
            "es_normal": p_value > 0.05,
            "observaciones": len(datos),
        }

    @staticmethod
    def generar_reporte_estadistico(df, nivel="genus", top_n=10):
        """
        Genera un reporte estadístico completo.
        """
        if df.empty:
            return None

        top_df = df.nlargest(top_n, "%_hits")
        
        return {
            "descriptivas": StatisticalAnalyzer.calcular_descriptivas(top_df),
            "normalidad": StatisticalAnalyzer.test_normalidad_shapiro(top_df),
            "taxa_analizados": len(top_df),
            "nivel": nivel,
        }

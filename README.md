TEMA: ANALISIS ...........
# Sistema Web de Análisis Comparativo de Perfiles Microbianos (16S & ITS)

Este sistema está diseñado para el análisis bioinformático y la visualización de datos metagenómicos procedentes de suelos agrícolas. Permite transformar resultados taxonómicos brutos en reportes interpretativos para la toma de decisiones en agricultura de precisión.

## 📋 Descripción del Proyecto
Plataforma orientada a investigadores y agrónomos para la comparación de la biodiversidad microbiana en cultivos específicos, permitiendo diferenciar el impacto del microbioma según la variedad o el clon del cultivo (ej. Cacao CCN51 vs. Otros clones).

## ✨ Funcionalidades Principales

### 1. Gestión de Muestras Agrícolas
*   **Registro Estructurado:** Asociación de muestras a cultivos, variedades o clones específicos.
*   **Segmentación Detallada:** Soporte para Cacao (CCN51, Clon 100, Clon 1), Café y otros productos agroindustriales.

### 2. Procesamiento y Pipeline Bioinformático
*   **Ingesta de Datos:** Carga de archivos de resultados moleculares (secuenciación 16S e ITS).
*   **Validación Automática:** Verificación de integridad de columnas taxonómicas: `Kingdom`, `Phylum`, `Class`, `Order`, `Family`, `Genus`, `Species`.
*   **Curación de Datos:** Limpieza, normalización y cálculo de abundancias (`num_hits` y `%_hits`).
*   **Agrupamiento Multinivel:** Clasificación jerárquica desde Reino hasta Especie.

### 3. Análisis Comparativo y Visualización
*   **Rankings de Abundancia:** Generación de Top 5, 10, 25 y 50 de microorganismos presentes.
*   **Análisis Diferencial:** 
    *   Comparativa entre muestras de una misma especie.
    *   Identificación de microorganismos **Dominantes**, **Compartidos** (Core) y **Exclusivos**.
*   **Clasificación Funcional:** Categorización de microorganismos según su rol biológico:
    *   ✅ **Benéficos**
    *   ⚠️ **Potencialmente Fitopatógenos**
    *   ⚪ **Sin Clasificación**

### 4. Salida de Resultados
*   Generación de tablas dinámicas.
*   Gráficos interactivos de composición taxonómica.
*   Reportes interpretativos para usuarios finales.


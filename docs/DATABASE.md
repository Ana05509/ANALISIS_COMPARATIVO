# 💾 Database Design & Schema - TerraBioLab

**Versión:** 1.0  
**Última actualización:** Mayo 2026  
**Estado:** Production-Ready

---

## 📋 Tabla de Contenidos

1. [Entity-Relationship Diagram](#entity-relationship-diagram)
2. [Schema Definition](#schema-definition)
3. [Data Relationships](#data-relationships)
4. [Normalization](#normalization)
5. [Indexing Strategy](#indexing-strategy)
6. [Performance Considerations](#performance-considerations)
7. [Migration Guide](#migration-guide)
8. [Backup & Recovery](#backup--recovery)

---

## 🔄 Entity-Relationship Diagram

```
┌──────────────────┐
│     Cultivo      │
├──────────────────┤
│ id (PK)          │
│ nombre (UNIQUE)  │
│ descripcion      │
│ fecha_creacion   │
└────────┬─────────┘
         │ (1:N)
         │
┌────────▼──────────────────┐
│   VariedadClon            │
├───────────────────────────┤
│ id (PK)                   │
│ cultivo_id (FK)           │
│ nombre                    │
│ (UNIQUE: cultivo_id, nombre)
└────────┬──────────────────┘
         │ (1:N)
         │
┌────────▼──────────────────────┐
│    MuestraSuelo               │
├───────────────────────────────┤
│ id (PK)                       │
│ codigo (UNIQUE)               │
│ cultivo_id (FK, PROTECT)      │
│ variedad_clon_id (FK, SET_NULL)
│ tipo_muestra (default: Suelo) │
│ observaciones                 │
│ fecha_registro (auto_now_add) │
│ fecha_muestreo                │
│ profundidad_cm                │
│ latitud                       │
│ longitud                      │
└────────┬───────────────────────┘
         │ (1:N)
         │
┌────────▼─────────────────────────┐
│   ArchivoMolecular                │
├───────────────────────────────────┤
│ id (PK)                           │
│ muestra_id (FK, CASCADE)          │
│ tipo_analisis (16S, ITS)          │
│ archivo (FileField)               │
│ fecha_carga (auto_now_add)        │
│ tamaño_bytes                      │
│ md5_hash                          │
│ usuario_id (FK)                   │
└────────┬────────────────────────────┘
         │ (1:N)
         │
┌────────▼────────────────────────────┐
│  ResultadoTaxonomico                │
├─────────────────────────────────────┤
│ id (PK)                             │
│ archivo_id (FK, CASCADE)            │
│ kingdom                             │
│ phylum                              │
│ class (tax_class)                   │
│ order                               │
│ family                              │
│ genus                               │
│ species                             │
│ num_hits (default: 0)               │
│ porcentaje_hits (default: 0)        │
│ fecha_creacion (auto_now_add)       │
│ (INDEX: archivo_id, genus, species)│
└─────────────────────────────────────┘

┌──────────────────────────────┐
│ CatalogoMicroorganismo        │
├──────────────────────────────┤
│ id (PK)                      │
│ nombre (UNIQUE)              │
│ nivel (genus, family, ...)   │
│ clasificacion                │
│   (benefico,                 │
│    fitopatogeno,             │
│    neutral,                  │
│    sin_clasificar)           │
│ descripcion                  │
│ referencia (DOI, PMID)       │
└──────────────────────────────┘

┌──────────────────────────────┐
│ Usuario (extends User)       │
├──────────────────────────────┤
│ id (PK)                      │
│ username (UNIQUE)            │
│ email (UNIQUE)               │
│ password (hashed)            │
│ rol (admin, tecnico,         │
│      agricultor)             │
│ is_active                    │
│ date_joined                  │
│ last_login                   │
└──────────────────────────────┘
```

---

## 📊 Schema Definition

### Table: Cultivo

Representa tipos de cultivos agrícolas.

```sql
CREATE TABLE analisis_cultivo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Índices:**
- `UNIQUE (nombre)` - Evita cultivos duplicados

**Ejemplos:**
- Cacao (Theobroma cacao)
- Café (Coffea spp.)
- Maní (Arachis hypogaea)

---

### Table: VariedadClon

Variedades o clones específicos dentro de un cultivo.

```sql
CREATE TABLE analisis_variedadclon (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cultivo_id INTEGER NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    FOREIGN KEY (cultivo_id) REFERENCES analisis_cultivo(id) ON DELETE CASCADE,
    UNIQUE (cultivo_id, nombre)
);
```

**Constraint:** Composición de cultivo_id + nombre única  
**Ejemplos:**
- Cacao → CCN51, ICS95
- Café → Bourbon, Typica, Geisha

---

### Table: MuestraSuelo

Información de muestras de suelo tomadas de campos.

```sql
CREATE TABLE analisis_muestrasuelo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo VARCHAR(50) NOT NULL UNIQUE,
    cultivo_id INTEGER NOT NULL,
    variedad_clon_id INTEGER,
    tipo_muestra VARCHAR(50) NOT NULL DEFAULT 'Suelo',
    observaciones TEXT,
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_muestreo DATE,
    profundidad_cm INTEGER,
    latitud DECIMAL(9, 6),
    longitud DECIMAL(9, 6),
    FOREIGN KEY (cultivo_id) REFERENCES analisis_cultivo(id) 
        ON DELETE PROTECT,
    FOREIGN KEY (variedad_clon_id) REFERENCES analisis_variedadclon(id) 
        ON DELETE SET_NULL
);
```

**Constraints:**
- cultivo_id: PROTECT (no puede eliminarse si hay muestras)
- variedad_clon_id: SET_NULL (opcional)
- codigo UNIQUE (identificación única de muestra)

**Campos Geoespaciales:**
- latitud, longitud (coordenadas GPS)
- profundidad_cm (profundidad de muestreo)

---

### Table: ArchivoMolecular

Archivos de secuenciación (16S o ITS).

```sql
CREATE TABLE analisis_archivomolecular (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    muestra_id INTEGER NOT NULL,
    tipo_analisis VARCHAR(10) NOT NULL CHECK (tipo_analisis IN ('16S', 'ITS')),
    archivo VARCHAR(100) NOT NULL,
    fecha_carga TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tamaño_bytes INTEGER,
    md5_hash VARCHAR(32),
    usuario_id INTEGER NOT NULL,
    FOREIGN KEY (muestra_id) REFERENCES analisis_muestrasuelo(id) 
        ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES auth_user(id)
);
```

**Campos:**
- tipo_analisis: '16S' (rRNA bacteriano) o 'ITS' (hongos)
- archivo: Path en media/archivos/
- md5_hash: Verificación de integridad

---

### Table: ResultadoTaxonomico

Resultado de clasificación taxonómica por línea de secuencia.

```sql
CREATE TABLE analisis_resultadotaxonomico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archivo_id INTEGER NOT NULL,
    kingdom VARCHAR(100),
    phylum VARCHAR(100),
    tax_class VARCHAR(100),
    "order" VARCHAR(100),
    family VARCHAR(100),
    genus VARCHAR(100),
    species VARCHAR(100),
    num_hits DECIMAL(10, 2) NOT NULL DEFAULT 0,
    porcentaje_hits DECIMAL(5, 2) NOT NULL DEFAULT 0,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (archivo_id) REFERENCES analisis_archivomolecular(id) 
        ON DELETE CASCADE
);
```

**Columnas Taxonómicas:**
- Niveles taxonómicos estándar (Linné)
- genus: Clave para clasificación funcional
- species: Especificidad máxima

**Índices (CRÍTICOS para performance):**
```sql
CREATE INDEX idx_resultado_archivo_id ON analisis_resultadotaxonomico(archivo_id);
CREATE INDEX idx_resultado_genus ON analisis_resultadotaxonomico(genus);
CREATE INDEX idx_resultado_genus_species 
    ON analisis_resultadotaxonomico(genus, species);
CREATE INDEX idx_resultado_archivo_genus_porcentaje 
    ON analisis_resultadotaxonomico(archivo_id, genus, porcentaje_hits);
```

---

### Table: CatalogoMicroorganismo

Catálogo de clasificación funcional (benéficos vs patógenos).

```sql
CREATE TABLE analisis_catalogomicroorganismo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    nivel VARCHAR(20) NOT NULL DEFAULT 'genus',
    clasificacion VARCHAR(20) NOT NULL CHECK (
        clasificacion IN ('benefico', 'fitopatogeno', 'neutral', 'sin_clasificar')
    ),
    descripcion TEXT,
    referencia VARCHAR(200),
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Clasificaciones Funcionales:**

| Clasificación | Descripción | Ejemplos |
|---|---|---|
| **benefico** | Promueve crecimiento vegetal (PGPR) | Bacillus, Pseudomonas, Rhizobium |
| **fitopatogeno** | Causa enfermedad en plantas | Moniliophthora, Phytophthora, Fusarium |
| **neutral** | Sin efecto conocido | Varios Actinobacteria |
| **sin_clasificar** | No determinado | Nuevas especies |

---

### Table: Usuario (extends Django User)

Django AbstractUser + rol personalizado.

```sql
CREATE TABLE auth_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    password VARCHAR(128) NOT NULL,
    last_login DATETIME,
    is_superuser BOOLEAN NOT NULL DEFAULT 0,
    username VARCHAR(150) NOT NULL UNIQUE,
    first_name VARCHAR(150),
    last_name VARCHAR(150),
    email VARCHAR(254) NOT NULL UNIQUE,
    is_staff BOOLEAN NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    date_joined DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rol VARCHAR(20) NOT NULL DEFAULT 'tecnico' CHECK (
        rol IN ('admin', 'tecnico', 'agricultor')
    )
);
```

**Roles:**
- **admin:** Acceso total, gestión de usuarios
- **tecnico:** Carga archivos, análisis
- **agricultor:** Visualización de reportes

---

## 🔗 Data Relationships

### 1:N Relationships

| Parent | Child | Constraint | Cascade |
|--------|-------|-----------|---------|
| Cultivo | VariedadClon | UNIQUE(cultivo_id, nombre) | CASCADE |
| Cultivo | MuestraSuelo | - | PROTECT |
| VariedadClon | MuestraSuelo | - | SET_NULL |
| MuestraSuelo | ArchivoMolecular | - | CASCADE |
| ArchivoMolecular | ResultadoTaxonomico | - | CASCADE |

### Reference Relationships

| Source | Target | Type |
|--------|--------|------|
| ResultadoTaxonomico.genus | CatalogoMicroorganismo.nombre | Lookup |
| ArchivoMolecular.usuario_id | auth_user.id | Foreign Key |

---

## ✅ Normalization

### Primera Forma Normal (1NF)
✅ Todos los atributos son atómicos  
✅ Sin repeticiones de grupos

### Segunda Forma Normal (2NF)
✅ 1NF cumplido  
✅ Todos los atributos no-clave dependen completamente de la clave primaria

### Tercera Forma Normal (3NF)
✅ 2NF cumplido  
✅ Sin dependencias transitivas

**Ejemplo de Normalización:**
```
❌ MAL: MuestraSuelo.cultivo_nombre (redundante con Cultivo.nombre)
✅ BIEN: MuestraSuelo.cultivo_id (FK a Cultivo)
```

---

## 🚀 Indexing Strategy

### Índices Críticos (Performance)

```sql
-- Query: Obtener resultados por archivo
CREATE INDEX idx_resultado_archivo_id 
    ON analisis_resultadotaxonomico(archivo_id);

-- Query: Comparación por género
CREATE INDEX idx_resultado_genus 
    ON analisis_resultadotaxonomico(genus);

-- Query: Búsqueda taxonómica específica
CREATE INDEX idx_resultado_genus_species 
    ON analisis_resultadotaxonomico(genus, species);

-- Query: Comparación con ordenamiento
CREATE INDEX idx_resultado_composite 
    ON analisis_resultadotaxonomico(
        archivo_id, genus, porcentaje_hits DESC
    );
```

### Índices Secundarios

```sql
-- Query: Historial por usuario
CREATE INDEX idx_archivo_usuario 
    ON analisis_archivomolecular(usuario_id);

-- Query: Muestras por cultivo
CREATE INDEX idx_muestra_cultivo 
    ON analisis_muestrasuelo(cultivo_id);

-- Query: Búsqueda de muestras
CREATE INDEX idx_muestra_codigo 
    ON analisis_muestrasuelo(codigo);
```

### SQLite vs PostgreSQL

**SQLite (Development):**
- Índices automáticos en UNIQUE
- Índices simples suficientes

**PostgreSQL (Production):**
```sql
-- Índices más avanzados
CREATE INDEX idx_resultado_genus_btree 
    ON analisis_resultadotaxonomico(genus) USING BTREE;

CREATE INDEX idx_resultado_porcentaje_gin 
    ON analisis_resultadotaxonomico(porcentaje_hits);

-- Índices parciales (PostgreSQL feature)
CREATE INDEX idx_resultado_abundant 
    ON analisis_resultadotaxonomico(archivo_id, genus) 
    WHERE porcentaje_hits > 1.0;
```

---

## 📈 Performance Considerations

### Query Optimization

**Problema:** Consultas lentas al comparar muestras

```python
# ❌ LENTO: N+1 queries
resultados = ResultadoTaxonomico.objects.filter(archivo__id=archive_id)
for resultado in resultados:
    print(resultado.archivo.muestra.cultivo.nombre)  # Query adicional

# ✅ RÁPIDO: Select related
resultados = ResultadoTaxonomico.objects.filter(
    archivo__id=archive_id
).select_related(
    'archivo__muestra__cultivo',
    'archivo__muestra__variedad_clon'
)
```

### Data Volume Estimates

| Table | Rows (1M samples) | Size | Notes |
|-------|-------------------|------|-------|
| Cultivo | 10 | <1KB | Referencia |
| VariedadClon | 50 | <1KB | Referencia |
| MuestraSuelo | 1M | 100MB | Grow linear |
| ArchivoMolecular | 2M | 50MB | 2 archivos/muestra |
| ResultadoTaxonomico | 50M | 2GB | 25 resultados/archivo |
| CatalogoMicroorganismo | 5K | 1MB | Referencia |

**Storage Estimate (PostgreSQL):**
- Total: ~2.2 GB para 1M muestras
- Con índices: ~3.5 GB
- Con backups: ~7 GB

---

## 🔄 Migration Guide

### SQLite → PostgreSQL

#### 1. Setup PostgreSQL

```bash
# Crear base de datos
createdb terrábiolab
psql terrábiolab -c "CREATE EXTENSION IF NOT EXISTS uuid-ossp;"
```

#### 2. Instalar Driver

```bash
pip install psycopg2-binary
```

#### 3. Actualizar settings.py

```python
# config/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'terrábiolab',
        'USER': 'postgres',
        'PASSWORD': 'tu_contraseña',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

#### 4. Ejecutar Migrations

```bash
python manage.py migrate --plan  # Ver cambios
python manage.py migrate          # Ejecutar
```

#### 5. Transferir Datos

```bash
# Dumping de SQLite
python manage.py dumpdata > data_backup.json

# Restore a PostgreSQL
python manage.py loaddata data_backup.json

# Verificación
python manage.py dbshell
\dt              # Listar tablas
SELECT COUNT(*) FROM analisis_resultadotaxonomico;  # Contar registros
```

---

## 💾 Backup & Recovery

### Backup Strategy

```bash
# PostgreSQL full backup
pg_dump terrábiolab > backup_$(date +%Y%m%d_%H%M%S).sql

# Incremental (si la extensión lo soporta)
pg_dump --format=custom > backup_full.dump

# Backup de archivos
tar -czf media_backup_$(date +%Y%m%d).tar.gz media/
```

### Recovery Procedure

```bash
# Restore PostgreSQL
psql -d terrábiolab < backup_20260515_143022.sql

# Restore archivos
tar -xzf media_backup_20260515.tar.gz

# Verificación
python manage.py check
python manage.py migrate --plan  # Debe estar vacío
```

---

## 📝 Data Dictionary

| Column | Type | Constraint | Description |
|--------|------|-----------|--|
| Cultivo.nombre | VARCHAR(100) | UNIQUE, NOT NULL | Nombre científico del cultivo |
| MuestraSuelo.codigo | VARCHAR(50) | UNIQUE, NOT NULL | Identificador único de muestra |
| ArchivoMolecular.tipo_analisis | VARCHAR(10) | CHECK, NOT NULL | '16S' o 'ITS' |
| ResultadoTaxonomico.genus | VARCHAR(100) | INDEX | Género taxonómico |
| ResultadoTaxonomico.porcentaje_hits | DECIMAL(5,2) | NOT NULL | Abundancia relativa (%) |
| CatalogoMicroorganismo.clasificacion | VARCHAR(20) | CHECK, NOT NULL | benefico, fitopatogeno, neutral |

---

## 🎯 Next Steps

1. **Phase 1:** Completar tests contra SQLite
2. **Phase 2:** Configur PostgreSQL localmente
3. **Phase 3:** Migrate datos y verificar integridad
4. **Phase 4:** Load testing y optimization

---

**Last Updated:** May 2026  
**Version:** 1.0  
**Status:** Production-Ready  
**Database:** SQLite (dev) → PostgreSQL (prod)

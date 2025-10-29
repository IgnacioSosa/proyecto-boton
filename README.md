# Sistema de Registro de Horas Versión 4.0

Aplicación web desarrollada con Streamlit para el registro y visualización de horas de trabajo, con funcionalidades avanzadas de administración de usuarios y gestión completa de datos. La versión 4.0 introduce mejoras significativas en manejo de errores, normalización de datos, ordenamiento, asignación flexible de técnicos, gestión de nómina y una interfaz completamente reorganizada.

## 🚀 Novedades y Cambios en v4.0

### Interfaz y Visualizaciones Mejoradas
- **Nueva organización de pestañas**: Separación clara entre visualizaciones por departamento y gestión de registros.
- **Pestaña unificada "📋 Tabla de Registros"**: Centraliza la visualización, importación y gestión de todos los registros.
- **Métricas por departamento**: Cada departamento tiene sus propias pestañas con 4 tipos de análisis:
  - 📊 Horas por Cliente (con filtros por técnico)
  - 📊 Tipos de Tarea (con análisis detallado)
  - 📊 Grupos (distribución y métricas)
  - 📊 Horas por Usuario (comparativas y detalles)
- **Filtros avanzados de fecha**: Mes actual, mes específico, período personalizado y total acumulado.
- **Gráficos interactivos mejorados**: Visualizaciones con Plotly más detalladas y responsivas.

### Gestión de Registros Centralizada
- **Importación unificada**: Subida de archivos Excel desde la pestaña principal de registros.
- **Edición y gestión**: Funcionalidades completas de CRUD (crear, leer, actualizar, eliminar) integradas.
- **Filtrado inteligente**: Selección por departamento con filtros de fecha aplicados automáticamente.
- **Tabla responsiva**: Visualización optimizada con paginación y ordenamiento.

### Validación y Manejo de Datos
- **Normalización robusta**: Manejo de acentos y variaciones comunes en nombres y datos.
- **Detección de errores mejorada**: Categorización clara de errores en importación desde Excel.
- **Prevención de fallos**: Filtrado seguro de fechas vacías y validación antes de procesar.
- **Mapeo flexible de columnas**: Detección automática de formatos diferentes en archivos Excel.
- **Ordenamiento consistente**: Clientes ordenados por ID en todas las vistas y consultas.

### Asignación y Gestión Avanzada
- **Asignación flexible de técnicos**: Umbral reducido (50%) con coincidencia basada en normalización.
- **Diagnóstico detallado**: Información clara sobre asignaciones no realizadas.
- **Gestión de nómina mejorada**: Validación de campos obligatorios y generación automática de roles.
- **Arquitectura modular**: Separación clara de responsabilidades entre módulos.

### Sistema de Logging Mejorado
- **Logging separado por tipo**:
  - `logs/sql/sql_errors.log` - Errores de base de datos
  - `logs/app/app_errors.log` - Errores de aplicación
- **Diagnóstico más claro**: Mensajes de error más informativos y trazabilidad mejorada.

## 📋 Características Principales

### Funcionalidades Core
- **Registro de horas**: Sistema completo con validaciones y prevención de duplicados.
- **Visualizaciones interactivas**: Gráficos de Plotly con múltiples vistas y filtros.
- **Administración completa**: Gestión de usuarios, clientes, tipos de tareas, modalidades, técnicos, roles y grupos.
- **Importación inteligente**: Procesamiento de archivos Excel con normalización automática.
- **Asignación automática**: Matching inteligente de registros a usuarios basado en nombres de técnicos.

### Módulos de Administración
- **👥 Usuarios**: Gestión completa de cuentas, roles y permisos.
- **🏢 Clientes**: Administración de empresas y proyectos.
- **📋 Tipos de Tarea**: Categorización y gestión de actividades.
- **🔧 Modalidades**: Configuración de tipos de trabajo (presencial, remoto, etc.).
- **🏛️ Departamentos**: Organización por áreas de trabajo.
- **👨‍💼 Planificación**: Asignación y programación de recursos.
- **👥 Grupos**: Organización de equipos de trabajo.
- **💰 Nómina**: Gestión de pagos y reportes financieros.

### Dashboards Especializados
- **Panel de Administración**: Vista completa con métricas y gestión.
- **Dashboard de Usuario**: Interfaz simplificada para registro personal.
- **Visor de Datos**: Consultas y reportes avanzados.

## 🛠️ Requisitos

### Dependencias del Sistema
- **Python 3.8+**
- **PostgreSQL 14+** (recomendado)

### Librerías Python
- **streamlit** - Framework web principal
- **pandas** - Manipulación de datos
- **plotly** - Visualizaciones interactivas
- **bcrypt** - Encriptación de contraseñas
- **openpyxl** - Importación de archivos Excel
- **python-dotenv** - Gestión de variables de entorno
- **psycopg2-binary** - Conexión a PostgreSQL
- **pyotp** y **qrcode** - Autenticación de dos factores (opcional)

## 📦 Instalación

### Prerrequisitos
- Tener PostgreSQL instalado y en ejecución.
- Contar con un usuario de PostgreSQL con permisos para crear bases de datos (CREATE DATABASE), o crear la base de datos manualmente (ver sección opcional).

1) Clonar el repositorio
```bash
git clone [url-del-repositorio]
```

2) Entrar al proyecto
```bash
cd proyecto-boton
```

3) Crear entorno virtual (Windows)
```bash
python -m venv venv
```

4) Activar entorno virtual (Windows)
```bash
venv\Scripts\activate


5) Instalar dependencias
```bash
pip install -r requirements.txt
```

6) Configurar variables de entorno (.env)
Crea el archivo `.env` en la raíz del proyecto con:
   
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=trabajo_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres  

7) Regenerar e inicializar la base de datos (modo automático)
```bash
python regenerate_database.py --auto
```
- Se crearán las tablas y datos iniciales.
- Usuario por defecto: admin
- Contraseña: admin

8) Ejecutar la aplicación
```bash
streamlit run app.py
```

### (Opcional) Crear base de datos/usuario manualmente
Si tu usuario de PostgreSQL no tiene permisos de creación de bases de datos:
- Crear la base de datos:
```bash
psql -U postgres -c "CREATE DATABASE trabajo_db;"
```
- Conceder permisos al usuario (si usas otro usuario):
```bash
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE trabajo_db TO postgres;"
```

### (Opcional) Ejecutar pruebas
```bash
pytest -q
```

## 🔧 Configuración Adicional

### Estructura de Archivos Excel (Importación)
Para importar registros desde Excel, se recomienda incluir estas columnas (el sistema realiza mapeos y normalización para formatos comunes):
- Fecha (DD/MM/YYYY)
- Técnico
- Cliente
- Tipo tarea
- Modalidad
- Tiempo
- Breve Descripción

El sistema intentará detectar columnas equivalentes y normalizarlas; si faltan datos críticos o hay incoherencias, mostrará mensajes de advertencia y no procesará filas inválidas.

### Estructura del Proyecto (resumen)
- app.py: Punto de entrada de la aplicación Streamlit.
- modules/: Módulos principales (base de datos, panel de administración, dashboards, utilidades, etc.).
- logs/: Carpeta de logs (errores SQL y de aplicación).
- regenerate_database.py: Regeneración/Inicialización completa de la base de datos PostgreSQL.
- requirements.txt: Dependencias del proyecto.
- tests/: Pruebas unitarias.

## 🐛 Correcciones destacadas en v4.0

- Manejo mejorado para evitar fallos por columnas de Excel no presentes o datos vacíos.
- Normalización de texto para coincidencias más fiables (manejo de acentos y variaciones).
- Asignación de técnicos más flexible con umbral de coincidencia al 50%.
- Ordenamiento de clientes por ID de cliente en vistas y consultas.
- Separación y mejora del sistema de logging para diagnóstico más claro.
# Sistema de Registro de Horas

Versión actual: 1.2.22

Aplicación web desarrollada con Streamlit para el registro y visualización de horas de trabajo, con funcionalidades avanzadas de administración de usuarios y gestión completa de datos. La versión 4.0 introduce mejoras significativas en manejo de errores, normalización de datos, ordenamiento, asignación flexible de técnicos, gestión de nómina y una interfaz completamente reorganizada.

## 🧭 Versionado

- Modelo de versionado semántico simplificado MAJOR.MINOR.PATCH
- La versión visible en la interfaz se toma desde el archivo de configuración
- Para actualizar la versión, editar:
  - Archivo: [config.py](modules/config.py)
  - Línea: `APP_VERSION = 'X.Y.Z'`
  - La UI lee este valor y lo muestra en:
    - Sidebar (abajo, fijo): [ui_components.py](modules/ui_components.py)
    - Login (abajo a la derecha, fijo): [ui_components.py](modules/ui_components.py)

## 📒 Changelog

### 1.2.22
- **Sistema Integral de Notificaciones**:
  - **Usuarios Comerciales**:
    - Centro de notificaciones (campana) integrado en el dashboard.
    - Alertas para proyectos vencidos, del día y próximos a vencer.
    - Avisos emergentes (toasts) de resumen al iniciar sesión (una vez por sesión).
  - **Usuarios Técnicos**:
    - Monitoreo automático de carga horaria (mes en curso).
    - Alertas para días laborables (Lunes-Viernes) con menos de 4 horas registradas.
    - Visualización detallada en menú desplegable y aviso inicial.
  - **Administrador Técnico (Visor)**:
    - Tablero de control de cumplimiento del equipo técnico.
    - Notificaciones agrupadas por técnico con detalle de días incompletos.
    - Manejo robusto de fechas para compatibilidad entre formatos.
- **Mejoras de UI/UX**:
  - Alineación optimizada del botón de notificaciones con el encabezado del dashboard.
  - Control de estado de sesión para evitar repetición de toasts al navegar.
  - Clarificación visual de "Mes en curso" en todas las alertas de carga horaria.
- **Correcciones**:
  - Solución a error `TypeError` en funcionalidad de carga de Excel (`render_excel_uploader`).
  - Corrección de conflicto de tipos de datos (SQL/Python) en consultas de fechas.

### 1.2.2
- **Mejoras en Panel de Administración**:
  - Unificación del formulario de gestión de conexiones de base de datos.
  - Ahora es posible cambiar la contraseña del usuario de base de datos directamente desde la UI (`ALTER USER`).
  - Campo de confirmación de contraseña añadido para mayor seguridad.
  - Eliminación de secciones duplicadas para una interfaz más limpia.
  - Lógica robusta de actualización: primero intenta cambios en BD y luego actualiza configuración.
- **Módulo Comercial y Contactos**:
  - **Experiencia de Usuario (UX)**:
    - Solución a recargas de página innecesarias al seleccionar contactos mediante gestión de estado en URL.
    - Sincronización inteligente: Al crear un contacto desde una vista filtrada (ej. Cliente X), el formulario se pre-llena automáticamente con esa entidad.
    - Persistencia de datos en formulario de proyectos al alternar entre pestañas de creación (evita pérdida de datos al crear contactos al vuelo).
  - **Funcionalidad**:
    - Nueva sección "Proyectos Compartidos Conmigo" con filtros avanzados (estado, autor, cliente).
- **Mantenimiento**:
  - Optimización de `requirements.txt` eliminando dependencias no utilizadas y fijando versiones críticas.

### 1.2.1
- **Script de Base de Datos Mejorado**:
  - Nuevas opciones de utilidad en `regenerate_database.py`:
    - `--check-connection`: Verifica conectividad con PostgreSQL.
    - `--fix-hash`: Restablece la contraseña del usuario admin.
    - `--setup-data`: Inserta datos base sin borrar tablas.
  - Ayuda integrada completa con `python regenerate_database.py --help`.
- **Configuración de Proyectos**:
  - Nueva sección en Panel de Admin para configurar el **ID inicial de proyectos**.
  - Permite definir secuencias personalizadas (ej. comenzar IDs en 1000).

### 1.2.0
- **Reingeniería de Vista `adm_comercial`**:
  - Implementación de vista de tarjetas idéntica al departamento comercial.
  - **Filtros Avanzados**:
    - Filtrado por Vendedor asignado.
    - Búsqueda por nombre de proyecto.
    - Filtro múltiple de Estados.
    - Ordenamiento por fecha de cierre.
  - **Mejoras de UX**:
    - Paginación integrada (10 proyectos por página).
    - Indicadores visuales de alertas de vencimiento.
    - Navegación fluida manteniendo filtros activos.

### 1.1.7
- Texto de versión fijo en:
  - Barra lateral: pegado al borde inferior, no se mueve al scrollear
  - Pantalla de login: esquina inferior derecha, fijo
- La versión se obtiene desde `APP_VERSION` en configuración y se muestra como “Version: X.Y.Z”
- Ajustes de UI del login:
  - Logo con fallback a `assets/logo.png` si no existe `assets/Sigo_logo.png`
  - Reducción de espacios verticales y tabs “Login/Registro” más compactos
- Persistencia de sesión:
  - Firma HMAC y parámetros en la URL para mantener sesión entre recargas
  - Implementado en [ui_components.py]
- Notificaciones comerciales para el rol “adm_comercial”:
  - Toasts con proximidad de vencimiento y nombre de la persona asociada al proyecto
  - Límite de 5 toasts y resumen si hay más
  - Se eliminó la lista expandible de alertas en el dashboard
- Roles del sistema:
  - Asegurado el rol “adm_comercial” en la base de datos
  - Unificación de duplicados “Sin Rol/sin_rol” y actualización de referencias
  - Centralización de nombres de roles en constantes del sistema
  - Migraciones idempotentes ejecutadas al inicio de la app
- Perfil y seguridad en la barra lateral:
  - Edición de nombre, apellido y correo con sincronización del nombre en la tabla de técnicos
  - Cambio de contraseña con validaciones de complejidad y hash seguro
  - Gestión completa de 2FA: habilitar/deshabilitar, QR, códigos de recuperación
  - Estados y feedback mediante toasts y mensajes claros
- Configuración comercial:
  - Estados de proyecto y tipos de venta centralizados en configuración
  - Lógica de proximidad de vencimiento con cálculo de días y prioridades

Archivos clave:
- Configuración y versión: [config.py](modules/config.py)
- UI: versión visible en sidebar y login: [ui_components.py](modules/ui_components.py)
- Dashboard comercial/visor y toasts: [visor_dashboard.py](modules/visor_dashboard.py)
- Migraciones de roles y DB utilidades: [database.py](modules/database.py)
- Integración de migraciones al arranque: [app.py](app.py)

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
- PostgreSQL instalado y en ejecución
- Usuario de PostgreSQL con permisos para crear bases de datos

### Pasos de Instalación

1. **Clonar el repositorio**
```bash
git clone [url-del-repositorio]
cd proyecto-boton
```

2. **Crear y activar entorno virtual**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
Crear archivo `.env` en la raíz del proyecto (sin incluir credenciales reales en repositorios públicos):
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=trabajo_db
POSTGRES_USER=sigo
POSTGRES_PASSWORD=sigo
```

5. **Inicializar la base de datos**
```bash
python regenerate_database.py --auto
```
- Crea todas las tablas y datos iniciales
- **Usuario por defecto**: `admin`
- **Contraseña por defecto**: `admin`

6. **Ejecutar la aplicación**
```bash
streamlit run app.py
```

### Herramientas de Base de Datos
El script `regenerate_database.py` incluye varias utilidades de mantenimiento:

```bash
# Ver ayuda completa
python regenerate_database.py --help

# Regeneración automática (Borra y crea todo)
python regenerate_database.py --auto

# Utilidades sin borrado
python regenerate_database.py --check-connection  # Verificar conexión
python regenerate_database.py --fix-hash          # Arreglar login admin
python regenerate_database.py --setup-data        # Re-insertar datos base
```

### Configuración Manual de Base de Datos (Opcional)
Si el usuario de PostgreSQL no tiene permisos de creación:
```sql
-- Crear base de datos
CREATE DATABASE trabajo_db;

-- Conceder permisos
GRANT ALL PRIVILEGES ON DATABASE "sigo-db" TO sigo;
```

### Ejecutar Pruebas (Opcional)
```bash
pytest -q
```

## 📊 Uso del Sistema

### Para Administradores
1. **Acceder con credenciales de admin**
2. **Configurar departamentos** en Gestión > Departamentos
3. **Crear usuarios** y asignar roles en Gestión > Usuarios
4. **Configurar clientes y tipos de tarea** según necesidades
5. **Importar registros** desde la pestaña "📋 Tabla de Registros"
6. **Revisar métricas** en las pestañas de cada departamento

### Para Usuarios
1. **Acceder con credenciales asignadas**
2. **Registrar horas** desde el Dashboard de Usuario
3. **Consultar resúmenes** personales
4. **Revisar planificación** asignada

### Importación de Datos Excel
El sistema acepta archivos Excel con las siguientes columnas (detecta automáticamente variaciones):
- **Fecha** (DD/MM/YYYY)
- **Técnico** (nombre del usuario)
- **Cliente** (empresa o proyecto)
- **Tipo tarea** (categoría de actividad)
- **Modalidad** (presencial, remoto, etc.)
- **Tiempo** (horas trabajadas)
- **Breve Descripción** (detalles opcionales)

## 🏗️ Arquitectura del Proyecto

### Estructura de Directorios
```
proyecto-boton/
├── app.py                 # Punto de entrada principal
├── modules/               # Módulos del sistema
│   ├── admin_panel.py     # Panel de administración
│   ├── admin_visualizations.py  # Visualizaciones y métricas
│   ├── admin_records.py   # Gestión de registros
│   ├── user_dashboard.py  # Dashboard de usuario
│   ├── visor_dashboard.py # Visor de datos
│   ├── database.py        # Conexión y consultas DB
│   ├── auth.py           # Autenticación y seguridad
│   └── utils.py          # Utilidades generales
├── logs/                 # Sistema de logging
│   ├── app/              # Logs de aplicación
│   └── sql/              # Logs de base de datos
├── tests/                # Pruebas unitarias
├── requirements.txt      # Dependencias
└── regenerate_database.py # Inicialización de DB
```

### Módulos Principales
- **`admin_panel.py`**: Interfaz principal de administración
- **`admin_visualizations.py`**: Gráficos y métricas por departamento
- **`admin_records.py`**: CRUD completo de registros
- **`database.py`**: Capa de acceso a datos con PostgreSQL
- **`auth.py`**: Sistema de autenticación y autorización
- **`utils.py`**: Funciones auxiliares y validaciones

## 🔧 Configuración Avanzada

### Variables de Entorno Adicionales
```env
# Configuración de logging
LOG_LEVEL=INFO
LOG_TO_FILE=true

# Configuración de sesión
SESSION_TIMEOUT=3600

# Configuración de importación
MAX_UPLOAD_SIZE=50MB
ALLOWED_EXTENSIONS=xlsx,xls
```

### Personalización de Interfaz
- **Temas**: Configurables en `.streamlit/config.toml`
- **Colores**: Paletas personalizables en visualizaciones
- **Idioma**: Soporte para español (por defecto)

## 🐛 Solución de Problemas

### Errores Comunes
1. **Error de conexión a PostgreSQL**: Verificar credenciales en `.env`
2. **Fallos en importación Excel**: Revisar formato de columnas y datos
3. **Problemas de permisos**: Verificar roles de usuario en la base de datos

### Logs de Diagnóstico
- **Errores SQL**: `logs/sql/sql_errors.log`
- **Errores de aplicación**: `logs/app/app_errors.log`

### Regeneración de Base de Datos
En caso de problemas graves:
```bash
python regenerate_database.py --auto --force
```

## 📈 Mejoras Futuras

### Funcionalidades Planificadas
- **API REST**: Integración con sistemas externos
- **Reportes PDF**: Generación automática de informes
- **Notificaciones**: Sistema de alertas y recordatorios
- **Dashboard móvil**: Interfaz optimizada para dispositivos móviles
- **Integración calendario**: Sincronización con Google Calendar/Outlook

### Optimizaciones Técnicas
- **Cache de consultas**: Mejora de rendimiento
- **Compresión de datos**: Optimización de almacenamiento
- **Backup automático**: Sistema de respaldos programados

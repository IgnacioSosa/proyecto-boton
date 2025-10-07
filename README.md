# Sistema de Registro de Horas Versión 4.0

Aplicación web desarrollada con Streamlit para el registro y visualización de horas de trabajo, con funcionalidades avanzadas de administración de usuarios y gestión completa de datos. La versión 4.0 introduce mejoras significativas en manejo de errores, normalización de datos, ordenamiento, asignación flexible de técnicos y gestión de nómina.

## 🚀 Novedades y Cambios en v4.0

### Validación y Manejo de Datos
- Normalización robusta de columnas y nombres (manejo de acentos y variaciones comunes).
- Detección y categorización de errores en importación desde Excel con mensajes claros.
- Prevención de fallos por fechas vacías y filtrado seguro antes de procesar.
- Detección automática y flexible de columnas relevantes del Excel con mapeo de diferentes formatos.
- Ordenamiento consistente de clientes por ID de cliente en vistas y consultas.

### Asignación y Gestión
- Asignación flexible de técnicos con umbral reducido (50%) y coincidencia basada en normalización de texto.
- Diagnóstico detallado de asignaciones no realizadas (por ejemplo, puntuación insuficiente o ausencia de coincidencias).
- Gestión avanzada de nómina: validación de campos obligatorios, filtrado de inactivos y generación automática de roles.

### Arquitectura y Registro de Errores
- Arquitectura modular con separación clara de responsabilidades.
- Sistema de logging separado para errores SQL y de aplicación:
  - logs/sql/sql_errors.log
  - logs/app/app_errors.log

## 📋 Características Principales

- Registro de horas de trabajo con validaciones y prevención de duplicados.
- Visualización con gráficos interactivos de Plotly.
- Administración completa: usuarios, clientes, tipos de tareas, modalidades, técnicos, roles y grupos.
- Importación de datos desde Excel con normalización y manejo inteligente de errores.
- Asignación automática de registros a usuarios basándose en coincidencias de nombres de técnicos.
- Gestión de nómina con validaciones y generación automática de roles.
- Interfaz moderna, organizada y adaptable.

## 🛠️ Requisitos

- Python 3.8+
- Streamlit
- PostgreSQL (14+ recomendado)
- Pandas
- Plotly
- bcrypt
- openpyxl (para importación de Excel)
- python-dotenv
- psycopg2-binary (conexión a PostgreSQL)
- pyotp y qrcode (dependencias incluidas, aunque el 2FA puede estar deshabilitado)

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
```

5) Instalar dependencias
```bash
pip install -r requirements.txt
```

6) Configurar variables de entorno (.env)
Crea el archivo `.env` en la raíz del proyecto con:
   
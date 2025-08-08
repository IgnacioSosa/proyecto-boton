# Sistema de Registro de Horas Versión 3.0

Aplicación web desarrollada con Streamlit para el registro y visualización de horas de trabajo, con funcionalidades avanzadas de administración de usuarios y gestión completa de datos. Esta versión incluye una arquitectura completamente refactorizada y nuevas características mejoradas.

## 🚀 Nuevas Características v3.0

### Funcionalidades de Usuario
- **Dashboard Mejorado**: Interfaz reorganizada con pestañas para mejor navegación
- **Gestión de Registros**: Crear, editar y eliminar registros de horas propios
- **Visualización Avanzada**: Gráficos semanales interactivos con navegación por fechas
- **Asignación Automática**: Los registros se asignan automáticamente basándose en el nombre del técnico
- **Registros No Asignados**: Visualización y gestión de registros sin asignar que coinciden con el usuario

### Panel de Administración
- **Gestión Completa de Usuarios**: Crear, editar, activar/desactivar usuarios
- **Gestión de Datos Maestros**: 
  - Clientes (agregar, editar, eliminar)
  - Tipos de tareas (agregar, editar, eliminar)
  - Modalidades (agregar, editar, eliminar)
  - Técnicos (agregar, editar, eliminar)
- **Importación de Datos**: Carga masiva desde archivos Excel
- **Asignación Automática**: Herramienta para asignar registros basándose en nombres de técnicos
- **Gestión de Registros**: Editar y eliminar cualquier registro del sistema

### Mejoras Técnicas
- **Arquitectura Modular**: Código completamente refactorizado en módulos especializados
- **Mejor Manejo de Errores**: Validaciones mejoradas y mensajes de error más claros
- **Optimización de Base de Datos**: Consultas optimizadas y mejor estructura de datos
- **Interfaz Mejorada**: Diseño más intuitivo y responsive

## 📋 Características Principales

- ✅ Registro de horas de trabajo con validación de duplicados
- 📊 Visualización de datos con gráficos interactivos de Plotly
- 👥 Sistema completo de gestión de usuarios con roles
- 🔐 Autenticación segura con bcrypt
- 📈 Gráficos semanales con navegación temporal
- 📁 Importación masiva de datos desde Excel
- 🔄 Asignación automática de registros por nombre de técnico
- 🎯 Gestión completa de datos maestros (clientes, tipos, modalidades)
- 📱 Interfaz responsive y moderna

## 🛠️ Requisitos

- Python 3.8+
- Streamlit
- SQLite3
- Plotly
- Pandas
- bcrypt
- openpyxl (para importación de Excel)

## 📦 Instalación

1. **Clonar el repositorio**
   ```bash
   git clone [url-del-repositorio]
   cd proyecto-boton
2. Crear un entorno virtual:
   ```bash
   python -m venv venv
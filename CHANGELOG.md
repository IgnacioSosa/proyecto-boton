# Changelog

Todas las notas de versión y cambios importantes del sistema.

## 1.2.39
- **Experiencia de Usuario (UX)**:
  - **Feedback de Creación de Tratos**: Se movió el mensaje de confirmación ("Trato creado correctamente") al final del formulario para asegurar que sea visible para el usuario sin necesidad de scroll manual.
  - **Corrección de Scroll**: Se eliminó el comportamiento errático de auto-scroll al crear un trato.

## 1.2.38
- **Gestión de Clientes (Soft Delete)**:
  - **Desactivación vs. Eliminación**: Implementada la funcionalidad para "desactivar" clientes en lugar de eliminarlos físicamente. Esto preserva la integridad histórica de los registros mientras oculta clientes inactivos de los selectores de nuevos tratos/contactos.
  - **Filtrado Inteligente**: Los clientes desactivados no aparecen en formularios de creación pero se mantienen visibles en registros históricos y filtros de búsqueda.
- **Mejoras de UI/UX**:
  - **Botón "Carga Manual"**: Ajuste de diseño responsive en el formulario de creación de tratos para evitar que el botón se deforme o salte de línea en resoluciones variables.
  - **URLs Profesionales**: Limpieza de la barra de direcciones reemplazando parámetros con emojis por claves de texto limpio (ej. `nuevo_trato`, `contactos`), manteniendo los iconos visuales solo en la interfaz de navegación.
- **Correcciones de Navegación**:
  - **Redirección Admin**: Solucionado error donde el administrador comercial no era redirigido correctamente a la pestaña "Nuevo Trato" tras crear un contacto desde allí.
  - **Flujo de Creación de Contactos**: Corregido comportamiento del selector de contactos que disparaba involuntariamente la creación de un nuevo contacto al entrar a la pestaña si la lista estaba vacía.
- **Correcciones Técnicas**:
  - **Widgets Streamlit**: Solucionada advertencia de conflicto entre valores por defecto e índices en selectores dinámicos (`create_cliente`).
  - **Estabilidad de Pestañas**: Implementada validación defensiva en el selector de pestañas de proyectos para prevenir errores de API (`StreamlitAPIException`) por desajuste de valores en sesión.
  - **Corrección Crítica (Hotfix)**: Solucionado error de ejecución (`NameError`) por definición faltante de constantes de mapeo de URL en el módulo de proyectos comerciales.

## 1.2.37
- **Mejoras de Visualización**:
  - **Gráfico de Horas**: Rotación de etiquetas del eje X a -45 grados para evitar superposición de nombres largos.
- **Mejoras en Planificación**:
  - **Filtro de Departamentos**: Exclusión de roles administrativos (prefijo "adm_") en el selector de departamentos para una vista más limpia.
- **Correcciones de Base de Datos**:
  - **Auto-reparación de Esquema**: Implementada detección y creación automática de la columna `activa` en la tabla `marcas` para prevenir errores de consulta.

## 1.2.36
- **Cambio de Terminología Comercial**:
  - Renombrado el término "Proyecto" a **"Trato"** en toda la interfaz comercial y administrativa para alinearse mejor con el flujo de ventas.
  - Actualizados títulos de pestañas: "Nuevo Trato", "Mis Tratos", "Tratos Compartidos Conmigo", "Tratos Dpto Comercial".
  - Ajustados gráficos y notificaciones para reflejar el nuevo término.
- **Mejoras de UI/UX**:
  - **Limpieza de Formularios**: Corregido comportamiento en "Gestión de Marcas" donde el campo de nombre no se limpiaba tras agregar una marca exitosamente.
  - **Gestión de Marcas**: Añadida opción para habilitar/deshabilitar marcas en lugar de eliminarlas permanentemente, permitiendo mantener el historial de datos.
  - **Visualización de Moneda**: Actualizados selectores de moneda para mostrar "USD" y "ARS" de forma limpia, eliminando "EUR" y corrigiendo problemas de renderizado de emojis en Windows.
  - **Legibilidad**: Aumentado el tamaño de fuente en áreas de texto descriptivo para mejorar la lectura.

## 1.2.35
- **Generación de Usuarios**:
  - Opción para descargar planilla de credenciales (CSV) tras generar usuarios desde nómina.
  - Botón "No deseo generar usuarios" en el asistente de configuración para saltar el paso.
  - **Asistente de Configuración (Wizard)**:
  - **Persistencia Robusta**: Solucionado el cierre prematuro del asistente. Se implementó persistencia mediante parámetros de URL para mantener el paso activo incluso tras recargas del servidor (ej. al guardar configuración de entorno).
  - **Carga de Registros (Paso 4)**: Corregida la visibilidad del paso. Ahora siempre está disponible y no se oculta automáticamente, independientemente de si se generaron usuarios o no en el paso anterior.
  - **Generación de Usuarios (Paso 2)**:
    - Opción para descargar planilla de credenciales (CSV) tras generar usuarios.
    - Botón explícito "No deseo generar usuarios" para saltar el paso.
- **Gestión de Roles y Visualización**:
  - **Roles Automáticos**: Desactivada la creación automática de roles (y pestañas en el dashboard) basados en el campo "Cargo" de los empleados. Esto evita la saturación de pestañas indeseadas (ej. "Gerente", "Analista") y mantiene la organización limpia por Departamento.
- **Funcionalidades de Respaldo**:
  - **Gestión Integral**: Implementada la capacidad de **generar y restaurar backups** tanto desde el **Panel de Administrador** como desde el **Asistente de Configuración Inicial**, asegurando flexibilidad total para la administración de datos en cualquier etapa.
- **Mejoras de UI/UX**:
  - **Botones de Restauración**: Igualado el tamaño del botón "Restaurar Backup" con "Nuevo Despliegue" y añadida descripción explicativa para mayor claridad y simetría.
  - **Alineación Vertical**: Ajuste de CSS en el asistente de configuración para centrar verticalmente los textos descriptivos respecto a los botones de acción.
  - **Barra Lateral**: Reducción del tamaño del botón "Cerrar Sesión" para diferenciarlo de las acciones principales y optimizar el espacio visual.
- **Correcciones Críticas**:
  - **Restauración de Backup**: Solucionado error crítico por falta de columna `cuit` en la tabla `clientes`. Se fuerza la actualización del esquema antes de la inserción de datos.
  - **Interacción**: Solucionado el problema de doble clic necesario en el botón "Restaurar Backup" añadiendo recarga automática.

## 1.2.34
- **Gestión de Licencias**:
  - **Próximas Licencias**: Nueva sección en la pestaña de Licencias (para usuarios técnicos y administradores) que lista de manera ordenada las futuras ausencias programadas, detallando usuario, tipo y fechas.
- **Correcciones y Mejoras en Proyectos Comerciales**:
  - **Selector "Compartir con"**:
    - Solucionado error que mostraba el selector vacío al crear proyectos (se agregó import faltante `get_roles_dataframe`).
    - Eliminada supresión silenciosa de errores para facilitar el diagnóstico.
    - Ampliada la lógica para permitir compartir proyectos tanto con colegas del mismo rol como con usuarios del rol `adm_comercial`.
  - **Interfaz de Usuario (UI)**:
    - **Alineación de Campos**: Ajustada la disposición de los campos "Valor" y "Moneda" en los formularios de creación y edición para ocupar el 50% del ancho cada uno (ratio 1:1), mejorando la estética y usabilidad.
    - **Navegación**: Corregido comportamiento al cambiar entre pestañas "Mis Proyectos" y "Compartidos Conmigo", limpiando la selección activa para evitar mostrar datos del proyecto incorrecto.
- **Gestión de Contactos (Mejoras de UX/UI)**:
  - **Validación de Datos**:
    - **Nombres**: Bloqueo de caracteres numéricos para asegurar nombres válidos.
    - **Teléfonos**: Limpieza automática de caracteres no numéricos (guiones, espacios, paréntesis) y validación de contenido numérico.
    - **Emails**: Verificación estricta de formato de correo electrónico.
  - **Campos Obligatorios**: Indicadores visuales (*) y validación bloqueante para Nombre, Email, Teléfono y Entidad.
  - **Simplificación de Interfaz**:
    - **Selector de Entidad Unificado**: Reemplazo de los selectores separados de tipo y nombre por un único campo de búsqueda global que combina Clientes y Marcas, agilizando la carga de contactos.

## 1.2.3
- **Script de Regeneración de Base de Datos**:
  - **Primer Inicio Simplificado**: Implementación de contraseña por defecto (`sigo`) para el usuario de base de datos, facilitando la instalación desatendida o rápida.
  - **Validación Robusta**: Añadida lógica de verificación de credenciales antes de la generación del archivo `.env`, evitando configuraciones inválidas.
  - **Recuperación Automática**: Capacidad para detectar y reutilizar usuarios existentes con credenciales estándar.
- **Configuración del Sistema**:
  - **Rutas de Entorno**: Ajuste en el seteo de rutas en la configuración inicial para asegurar la correcta localización de recursos y módulos.
- **Mantenimiento de Código**:
  - **Limpieza de Configuración**: Eliminación definitiva de variables y referencias a SQLite en `modules/config.py`, consolidando PostgreSQL como el único motor de base de datos soportado.

## 1.2.27
- **Correcciones y Mejoras de Estabilidad**:
  - **Panel de Administración**: 
    - Solucionado error de ordenamiento de fechas en tabla de registros (orden cronológico real).
    - Corregido `KeyError: 'tipo'` al editar registros desde el panel admin.
  - **Panel de Usuario**:
    - Solucionado error `TypeError: strptime()` al editar registros con fechas Timestamp.
    - Corregido error de clave duplicada `new_hora_extra` en formulario.
    - Simplificación de etiqueta "Es hora extra" a "Hora extra".
  - **Consistencia de Datos**:
    - Unificación de nombres de técnicos (ej. "Ignacio martin Sosa") mediante alias persistentes.
    - Mantenimiento de consistencia de nombres tras regeneración de base de datos.
    - Solución a error de columna faltante `id_grupo` al guardar registros.
  - **Sistema**:
    - Inicialización robusta de variables de sesión (`username`).

## 1.2.26
- **Estandarización de Terminología y UI**:
  - **Renombrado de Pestañas**: La pestaña "Vacaciones" ahora se denomina **"Licencias"** tanto en el panel de usuario como en el de administrador técnico, para reflejar mejor su alcance ampliado.
  - **Consistencia Visual**: Actualización de todos los textos de la interfaz (botones, encabezados, selectores) para usar el término "Licencia" en lugar de "Ausencia" o "Vacaciones".
- **Mejoras en Lógica de Negocio**:
  - **Unificación de Comportamiento**: Garantía de que los tipos "Licencia" y "Día de Cumpleaños" hereden todas las propiedades automatizadas de las vacaciones:
    - Generación de registros de 8 horas.
    - Filtrado automático de días no laborables (Lunes a Viernes).
    - Actualización inmediata de la planificación semanal y cachés.

## 1.2.25
- **Gestión Avanzada de Ausencias**:
  - **Nuevos Tipos de Ausencia**: Soporte extendido para "Licencia" y "Día de Cumpleaños", además de "Vacaciones".
  - **Reglas de Negocio**: Restricción de 1 día para "Día de Cumpleaños".
  - **Visualización**: Colores distintivos para cada tipo de ausencia en la planificación (Naranja, Púrpura, Rosa).
- **Correcciones y Mejoras**:
  - **Sincronización**: Solucionado problema de actualización de caché de planificación al asignar ausencias desde el panel administrativo.
  - **Integridad de Datos**:
    - Los registros de ausencia generan automáticamente las modalidades y tareas correspondientes ocultas.
    - Restauración inteligente de la planificación por defecto al eliminar periodos.

## 1.2.24
- **Mejoras en Gestión de Vacaciones**:
  - **Edición de Periodos**:
    - Capacidad para modificar fechas de vacaciones existentes (Admin y Usuario).
    - Regeneración inteligente de registros: al cambiar fechas, se eliminan los registros antiguos y se crean los nuevos automáticamente.
    - Validación de integridad de fechas en la edición.

## 1.2.23
- **Gestión Integral de Vacaciones**:
  - **Nueva Pestaña "Vacaciones"**: Disponible para usuarios técnicos y administradores (`adm_tecnico`).
  - **Modo Vacaciones (Usuario)**:
    - Configuración de periodos de ausencia.
    - Generación automática de registros de horas (8hs diarias, Lunes a Viernes) bajo el cliente  y tarea "Vacaciones".
    - Exclusión de la tarea "Vacaciones" en la carga manual para evitar errores.
  - **Gestión Administrativa**:
    - Visualización global de técnicos actualmente de vacaciones.
    - Capacidad para asignar y eliminar periodos de vacaciones a cualquier miembro del equipo.
  - **Historial y Filtros**:
    - Visualización de periodos pasados y futuros.
    - Nuevo filtro por año para consultar historiales antiguos o planificaciones futuras.
- **Optimizaciones**:
  - Limpieza automática de caché tras cambios en vacaciones para actualización inmediata de gráficos y tablas.
  - Ajustes en la carga de registros para soportar autocompletado inteligente en periodos de ausencia.

## 1.2.22
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

## 1.2.2
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

## 1.2.1
- **Script de Base de Datos Mejorado**:
  - Nuevas opciones de utilidad en `regenerate_database.py`:
    - `--check-connection`: Verifica conectividad con PostgreSQL.
    - `--fix-hash`: Restablece la contraseña del usuario admin.
    - `--setup-data`: Inserta datos base sin borrar tablas.
  - Ayuda integrada completa con `python regenerate_database.py --help`.
- **Configuración de Proyectos**:
  - Nueva sección en Panel de Admin para configurar el **ID inicial de proyectos**.
  - Permite definir secuencias personalizadas (ej. comenzar IDs en 1000).

## 1.2.0
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

## 1.1.7
- Texto de versión fijo en:
  - Barra lateral: pegado al borde inferior, no se mueve al scrollear
  - Pantalla de login: esquina inferior derecha, fijo
- La versión se obtiene desde `APP_VERSION` en configuración y se muestra como “Version: X.Y.Z”
- Ajustes de UI del login:
  - Logo con fallback a `assets/logo.png` si no existe `assets/Sigo_logo.png`
  - Reducción de espacios verticales y tabs “Login/Registro” más compactos
- Persistencia de sesión:
  - Firma HMAC y parámetros en la URL para mantener sesión entre recargas
  - Implementado en `ui_components.py`
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


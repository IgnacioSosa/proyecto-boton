# Changelog

Todas las notas de versión y cambios importantes del sistema.

## 1.2.52
- **Interfaz de Usuario (UI)**:
  - **Optimización de Espacio Vertical**: Se eliminaron los márgenes superiores innecesarios (`padding-top`) y se ocultaron elementos del sistema (Header y Footer de Streamlit) para maximizar el área de trabajo útil, permitiendo que el contenido comience desde el borde superior de la ventana.

## 1.2.51
- **Estabilidad de Sesión**:
  - **Corrección de Logout**: Se solucionó un problema crítico donde el botón de "Cerrar Sesión" requería múltiples clics o provocaba un bucle de recarga. Esto ocurría porque la cookie de sesión persistente volvía a autenticar al usuario antes de ser eliminada. Ahora, el sistema ignora explícitamente la cookie durante el proceso de salida, garantizando un cierre de sesión inmediato y limpio.

## 1.2.5
- **Seguridad y Autenticación**:
  - **Cookies Seguras**: Implementación de autenticación persistente mediante Cookies HTTP encriptadas y firmadas digitalmente. Esto reemplaza el método anterior basado en parámetros URL, eliminando vulnerabilidades de *Session Hijacking*.
  - **Sesiones Robustas**: El sistema ahora mantiene la sesión activa incluso al refrescar la página (F5), mejorando significativamente la experiencia de usuario sin comprometer la seguridad.
  - **Corrección de Bugs**: Solucionado el error `StreamlitDuplicateElementKey` que ocurría al inicializar el gestor de cookies múltiples veces en una misma ejecución.
- **Interfaz de Usuario (UI)**:
  - **Etiquetas de Oficina (Chips)**: Rediseño completo de los indicadores de presencia en el banner "Hoy en la oficina". Ahora utilizan un estilo de píldora (`border-radius` completo) con colores de contraste optimizados para garantizar legibilidad tanto en modo claro como oscuro.
  - **Tooltips Nativos**: Se estandarizaron los tooltips en formularios comerciales utilizando el parámetro nativo `help` de Streamlit, mejorando la consistencia visual y el comportamiento en dispositivos móviles.

## 1.2.49
- **Carga Masiva de Clientes**:
  - **Corrección de Error Crítico**: Solucionado error `The truth value of a Series is ambiguous` que ocurría al procesar archivos con columnas duplicadas o al validar contra clientes existentes con estructuras de datos complejas.
  - **Deduplicación Inteligente**: Nueva lógica de coincidencia parcial para detectar clientes duplicados cuando el nombre varía ligeramente (ej: "Empresa S.A." vs "Empresa") y no se cuenta con CUIT. Esto previene la creación de múltiples registros para la misma entidad.
  - **Robustez**: Limpieza automática de columnas duplicadas en memoria para evitar conflictos en las validaciones internas.
- **Validación de Formularios**:
  - **Límites de Caracteres**: Se implementaron límites de caracteres en los formularios de registro de horas (Usuario y Admin) para asegurar la consistencia de los datos:
    - **Tarea Realizada**: Máximo 100 caracteres.
    - **Número de Ticket**: Máximo 20 caracteres.
    - **Descripción**: Máximo 250 caracteres.
  - **Valores Negativos**: Se bloqueó la posibilidad de ingresar importes negativos en la creación y edición de tratos comerciales tanto para el rol Comercial como Adm Comercial, asegurando la integridad de los datos financieros.
  - **Formato Decimal**: Se agregó una aclaración visual en el campo de "Valor" para indicar explícitamente el uso de la coma (,) como separador decimal, mejorando la experiencia de usuario y reduciendo errores de carga.
- **Mejoras Visuales (UI)**:
  - **Campo de Contraseña**: Se corrigió un error de visualización CSS en el campo de contraseña donde el ícono de visibilidad ("ojo") quedaba fuera del estilo del input o con fondo superpuesto. Ahora el campo se muestra integrado y limpio, con transparencia correcta en los elementos internos.
  - **Campo de Fecha**: Se aplicó la misma corrección de estilo al selector de fecha (`st.date_input`) para asegurar que el icono del calendario y el texto se muestren correctamente integrados dentro del contenedor oscuro.
  - **Corrección Modo Claro**: Se unificaron los estilos de las tarjetas de proyecto y formularios para respetar el tema claro (Light Mode). Anteriormente, ciertas vistas del Dashboard Comercial forzaban estilos de modo oscuro, causando problemas de legibilidad en fondos y desplegables. Ahora se utiliza una inyección CSS centralizada que adapta dinámicamente los colores según la preferencia del usuario.
  - **Etiquetas de Oficina**: Se rediseñaron los indicadores de presencia ("chips") en el banner "Hoy en la oficina" con un estilo de píldora (`border-radius` completo) y fondo transparente adaptable, garantizando una visualización correcta tanto en modo claro como oscuro.
  - **Tooltips de Formularios**: Se revirtió la implementación de tooltips HTML personalizados en los formularios de proyectos comerciales a favor del parámetro nativo `help` de Streamlit, mejorando la consistencia con el resto de la aplicación.
  - **Renderizado de Tablas**: Se corrigió un error de sintaxis HTML en las tablas de planificación que provocaba la visualización del texto `</div>` al pie del componente.

- **Mejoras Visuales y de UX (Wizard)**:
  - **Responsividad en Botones**: Se ajustó el diseño de los botones de generación de usuarios ("Iniciar Generación" vs "No deseo generar") para utilizar columnas de ancho equitativo (50% cada una). Esto soluciona problemas de desproporción visual en monitores de menor resolución.
- **Gestión de Registros (Admin)**:
  - **Claridad en Alertas**: Mejorada la advertencia de "Clientes no encontrados" durante la importación. Para listas cortas (hasta 5 clientes), los nombres ahora se muestran directamente en el mensaje de alerta, facilitando la identificación rápida sin clics adicionales.

## 1.2.48
- **Mejoras en la Experiencia de Inicio de Sesión**:
  - **Corrección de Temblor en UI**: Se solucionó el molesto desplazamiento visual ("temblor") al fallar el inicio de sesión. Esto se logró eliminando mensajes de error duplicados (uno genérico y otro detallado) y centralizando toda la lógica de notificaciones en el módulo de autenticación.
  - **Claridad en Errores**: Ahora se muestra un único mensaje claro y estable para cada situación (contraseña incorrecta, usuario no encontrado, cuenta bloqueada, etc.).
- **Mejoras en el Dashboard de Usuario**:
  - **Eliminación de Registros**: Se corrigió el problema de "doble clic" necesario para eliminar registros individuales.
  - **Refresco Automático**: Implementada actualización inmediata de la lista de registros tras una eliminación exitosa, mejorando la fluidez de la gestión diaria.

## 1.2.47
- **Gestión de Contactos (Favoritos y Recientes)**:
  - **Nueva Funcionalidad**: Se añadieron secciones de "Favoritos" y "Recientes" en la gestión de contactos, permitiendo acceso rápido a los contactos más utilizados.
  - **Vista Detallada**: Las tarjetas de favoritos ahora muestran información clave (Nombre, Puesto, Cliente) para facilitar la identificación.
  - **Sincronización Inteligente**: Al seleccionar un contacto desde estas listas, los filtros principales (Cliente/Marca) se actualizan automáticamente para reflejar el contexto del contacto seleccionado.
- **Mejoras de UX/UI (Contactos)**:
  - **Selector Unificado**: El selector de asignación de entidad (Cliente/Marca) en el formulario de contacto se ha unificado y limpiado, eliminando sufijos redundantes como "(Cliente)" para una lectura más clara.
  - **Corrección de Modales**: Solucionado un problema donde el modal de "Crear Contacto" aparecía incorrectamente al cambiar filtros de cliente.
  - **Estabilidad de Navegación**: Corregido un error que causaba cambios de pestaña inesperados al seleccionar un contacto en el dashboard comercial (`adm_comercial`).
- **Asistente de Configuración (Wizard)**:
  - **Gestión de Clientes (Nuevo Paso 3)**: Se integró un módulo completo de gestión de clientes (Alta/Baja/Modificación) dentro del flujo de configuración inicial, previo a la carga de registros.
  - **Carga Masiva Mejorada**:
    - **Soporte Extendido**: Agregado soporte para columnas 'Celular' y 'Web' (URL) en la importación Excel.
    - **Selección de Hojas**: Nueva capacidad para seleccionar la hoja específica del archivo Excel a procesar.
    - **Robustez**: Corrección de errores por columnas duplicadas y manejo seguro de datos faltantes en campos opcionales.
    - **Feedback de Usuario**: Mensajes de éxito persistentes y colapso automático del panel de carga tras un proceso exitoso.
  - **UX**: Reorganización de elementos para priorizar la tabla de clientes y botones de navegación en la parte superior.
- **Gestión de Registros y Métricas**:
  - **Integridad de Datos**: Se eliminó la creación automática de clientes desde la carga de métricas. Ahora se requiere la existencia previa del cliente, mejorando la calidad de la base de datos.
  - **Matching Inteligente**: Implementación de algoritmo de búsqueda jerárquica y normalizada para asociar registros.
- **Visualización y Gráficos**:
  - **Legibilidad de Clientes**: Los gráficos circulares ahora muestran nombres acortados de clientes (ej. primera palabra o sigla) para evitar saturación visual, manteniendo el nombre completo en el tooltip.
  - **Legibilidad de Usuarios**:
    - **Nombres Acortados**: Implementada lógica "Primer Nombre + Apellido Principal" en gráficos de barras.
    - **Orientación**: Etiquetas de eje X horizontales para facilitar la lectura.
  - **Corrección de Errores**: Solucionado error `ValueError: Length mismatch` en la generación de tablas de detalle de horas por usuario.

## 1.2.46
- **Mejoras de UX (Registro de Horas)**:
  - **Limpieza de Formulario**: Se solucionó un problema donde los campos del formulario de nuevo registro (tarea, ticket, descripción, tiempo) mantenían sus valores tras un guardado exitoso. Ahora se limpian automáticamente para facilitar la carga de múltiples registros.
- **Mejoras de UI (Panel de Administración)**:
  - **Diálogo de Restauración**: Se ajustaron los botones de confirmación "Cancelar" y "Restaurar" para tener dimensiones idénticas (ancho 1:1 y altura fija), mejorando la simetría visual y previniendo discrepancias de tamaño entre botones primarios y secundarios.
- **Mejoras de UX (Gestión Comercial)**:
  - **Selector de Clientes**: Corregido comportamiento del flujo de creación rápida de clientes. Al cancelar o cerrar la ventana de "+ Crear nuevo cliente", la selección de un cliente existente ya no reabre incorrectamente el formulario de creación.

## 1.2.45
- **Correcciones de Errores Críticos**:
  - **Registro de Horas**: Solucionado error `name 'nombre_completo_usuario' is not defined` al guardar un nuevo registro. Se reemplazó la variable no definida por `tecnico` para permitir la correcta asociación de departamentos en `get_or_create_grupo_with_tecnico_department_association`.
  - **Gestión de Modalidades**: Corregido error SQL en la eliminación de modalidades. Se actualizó la consulta de verificación de dependencias para usar la columna correcta `id_modalidad` en lugar de `modalidad_id`.
- **Mejoras en Visibilidad de Usuarios (Compartir Tratos)**:
  - **Corrección en Selector de Compartir**: Se solucionó un problema donde los usuarios con rol `adm_comercial` solo veían a otros administradores al intentar compartir un trato. Ahora, el selector incluye correctamente tanto a otros administradores (`adm_comercial`) como a los vendedores (`Dpto Comercial`), permitiendo una colaboración fluida entre la dirección y el equipo de ventas.

## 1.2.44
- **Estabilidad del Sistema (Backups)**:
  - **Corrección de Error de E/S**: Solucionado un problema crítico (`OSError: [Errno 5] Input/output error`) en la herramienta de restauración de backups que provocaba fallos en entornos de despliegue sin acceso a salida estándar (stdout).
  - **Mejora en Logging**: Se reemplazaron las salidas de consola (`print`) por un sistema de registro de errores robusto (`log_sql_error`) en el módulo de backups, asegurando que las advertencias y errores se guarden correctamente en los archivos de log sin interrumpir la ejecución.

## 1.2.43
- **Mejoras en Dashboard de Administración Comercial (adm_comercial)**:
  - **Navegación Interactiva y Redirecciones**:
    - **Campana de Notificaciones Inteligente**: Al hacer clic en las alertas de "Solicitudes de Clientes" o "Tratos Vencidos", el sistema redirige automáticamente a la pestaña y sub-pestaña correspondiente.
    - **Filtro Automático de Tratos**: Al hacer clic en una alerta de tratos vencidos de un vendedor específico, se redirige a la vista "Tratos Dpto Comercial" y se pre-selecciona automáticamente a ese vendedor en el filtro.
  - **Experiencia de Inicio de Sesión (Login)**:
    - **Notificaciones Inteligentes (Toasts)**: Al iniciar sesión, se muestra un resumen emergente de las alertas críticas (solicitudes pendientes y tratos vencidos).
    - **Control de Frecuencia**: Estas alertas aparecen solo una vez por sesión para evitar saturación visual en recargas posteriores.
    - **Agrupación de Alertas**: Las alertas de proyectos se agrupan por vendedor y se ordenan por gravedad, limitando la visualización a las 5 más importantes.
  - **Experiencia de Primer Inicio (Despliegue)**:
    - **Regeneración de Base de Datos Visual**: Incorporación de barra de progreso en tiempo real (`tqdm`) en el script de regeneración de base de datos para mejor feedback durante la instalación.
    - **Validaciones Robustas**: Verificación automática de conexión a PostgreSQL, detección inteligente de usuarios existentes y corrección automática de hashes de administrador.
  - **Modernización de UI**:
    - Reemplazo de menús desplegables (`selectbox`) por controles de pestañas segmentados (`segmented_control`) en la navegación interna (Clientes, Solicitudes), igualando la experiencia de usuario del panel de Administrador general.
  - **Estabilidad**:
    - Corrección de claves duplicadas en los botones de aprobación/rechazo de solicitudes de clientes para evitar errores de renderizado.

## 1.2.42
- **Mejoras Visuales (UI)**:
  - **Botón Editar Proyecto**: Se ajustó el tamaño del botón "Editar" en la vista de detalle de proyecto para igualar las dimensiones del botón "Eliminar", mejorando la consistencia visual y la facilidad de interacción (touch target), manteniendo su estilo de color original.
  - **Simplificación de Diálogos**: Se eliminaron los botones "Cancelar" en el diálogo de carga manual de clientes (tanto en la confirmación como en el formulario), optando por el uso estándar del botón de cierre ("X") del modal para limpiar la interfaz.
- **Flujo de Trabajo (UX)**:
  - **Creación Rápida de Clientes**: Se integró la opción "➕ Crear nuevo cliente" directamente dentro del menú desplegable de selección de clientes en el formulario de creación de tratos. Esto unifica la experiencia con la creación de contactos y reduce la dispersión de botones en la interfaz.
  - **Claridad en Botones**: Se renombró el botón externo "Carga manual" a "Crear nuevo cliente" (en los contextos donde aún aplica) para mayor claridad semántica.
- **Correcciones Técnicas**:
  - **Estabilidad de Selectores**: Se configuró el selector de clientes con `index=None` para evitar selecciones automáticas no deseadas que podían causar bucles en la apertura de diálogos modales.
  - **Cierre de Diálogos**: Se implementó un mecanismo robusto de cierre de diálogos modales mediante actualización de parámetros URL (`_close_dialog`), asegurando que la interfaz se refresque correctamente al finalizar o cancelar una acción.

## 1.2.41
- **Mejoras de UI/UX**:
  - **Limpieza de Formularios**: Corregido comportamiento en "Gestión de Marcas" donde el campo de nombre no se limpiaba tras agregar una marca exitosamente.
  - **Gestión de Marcas**: Añadida opción para habilitar/deshabilitar marcas en lugar de eliminarlas permanentemente, permitiendo mantener el historial de datos.
  - **Simplificación de Contactos**: Eliminado el campo "Dirección" de los formularios de creación/edición y vistas de detalle de contactos por no ser un dato necesario, agilizando la carga.
  - **Asignación de Contactos**: El campo "Entidad" en los formularios de contacto ahora permite seleccionar únicamente **Clientes**, eliminando la opción de Marcas para alinear el sistema con la estructura comercial.
- **Flujo de Trabajo Comercial**:
  - **Vista por Defecto**: Cambiada la pantalla inicial del usuario comercial a "Mis Tratos" (anteriormente "Nuevo Trato") para facilitar el acceso rápido a la gestión diaria.
  - **Ordenamiento de Tratos**: Se establece y documenta que los proyectos en el listado 'Mis Tratos' se muestran ordenados por defecto de forma descendente según su fecha de creación (los más recientes primero).
  - **Personalización de UI**: Se refactorizó el botón 'Editar' en la vista de detalle de proyectos para permitir la definición manual y explícita de sus parámetros de visualización.
- **Seguridad y Validaciones**:
  - **Unicidad de Clientes**: Implementada validación estricta de CUIT y Nombre en la carga manual de clientes para prevenir duplicados.
  - **Restricción de Base de Datos**: Añadida restricción de unicidad (`UNIQUE INDEX`) en la columna `cuit` de la tabla de clientes.
  - **Normalización de CUITs**: El sistema ahora almacena los CUITs únicamente como dígitos (sin guiones), independientemente de cómo los ingrese el usuario, garantizando consistencia en la base de datos.
  - **Validación de Teléfonos**: Integrada la librería `phonenumbers` para validar y formatear números de teléfono (estándar internacional, región por defecto AR) en los formularios de Clientes y Contactos, asegurando la calidad de los datos de contacto.
  - **Validación Estricta de Contactos**: Se hicieron obligatorios todos los campos en los formularios de contacto (Nombre, Apellido, Puesto, Email, Teléfono, Cliente). Además, se añadió validación para impedir el ingreso de números en el campo "Apellido".

## 1.2.40
- **Correcciones de Visualización (UI)**:
  - **Tarjetas de Tratos**: Solucionado el problema de renderizado HTML crudo en las etiquetas de estado ("pills") dentro de las tarjetas de "Mis Tratos" y paneles comerciales. Se corrigió el manejo de espacios en blanco en la plantilla HTML para garantizar que Streamlit interprete correctamente los estilos.

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

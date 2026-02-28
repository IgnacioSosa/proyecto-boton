# Changelog

Todas las notas de versión y cambios importantes del sistema.

## 1.2.67
- **Importación de Excel (Mejoras)**:
  - **Detección Inteligente de Contactos**: El sistema ahora detecta automáticamente columnas separadas de "Nombre" y "Apellido" en el Excel, las combina y crea/asocia el contacto correctamente al trato y cliente.
  - **Corrección de Loop Infinito**: Se solucionó el problema donde la carga de Excel se quedaba en un bucle "Procesando archivo..." mediante la limpieza automática del estado de la sesión tras una carga exitosa.
  - **Actualización de Registros Existentes**: Al volver a subir una planilla, el sistema detecta los Tratos por su ID y actualiza la información (ej. agregar contactos faltantes) en lugar de duplicar registros.
  - **Creación Automática de Marcas**: El sistema ahora detecta la columna "Marca" en el Excel de importación y crea/asocia la marca automáticamente al trato, evitando la necesidad de creación manual previa.
  - **Limpieza de Interfaz**: Se eliminó el mensaje redundante "Visualizando registros comerciales (Tratos)" para una vista más limpia.
  - **Formato Numérico**: Mejorada la detección de formatos numéricos (ej. 1.200 como 1200) para evitar valores incorrectos en los montos.
- **Gestión de Departamentos (Corrección de Duplicados)**:
  - **Normalización Robusta**: Se implementó una lógica de limpieza de nombres de roles para prevenir la creación de departamentos duplicados con prefijos redundantes (ej. `adm_adm_comercial`, `Dpto Comercial` vs `Comercial`). Ahora el sistema identifica y unifica variaciones de nombres automáticamente.
  - **Prevención en Origen**: La generación automática de roles desde nómina y la creación manual en el panel de administración ahora utilizan esta normalización para rechazar duplicados antes de su creación.
- **Roles y Nómina (Correcciones)**:
  - **Administración como Departamento**: Se corrigió el mapeo para que "Administración" cree `dpto_administracion` (departamento) y `adm_administracion` (administrador), evitando que el departamento quede mal catalogado como rol admin.
  - **Asignación de Roles `Adm_*`**: Al generar usuarios desde nómina, si el sector/departamento viene como `Adm_comercial`, `Adm_tecnico`, etc., ahora se asigna correctamente el rol `adm_*` en lugar de `dpto_*`.
  - **Reparación Automática**: Se agrega una corrección de arranque para mover usuarios no-admin mal asignados a `adm_administracion` hacia `dpto_administracion`.
- **Clientes (Carga Masiva)**:
  - **Validación de CUIT**: La carga masiva de clientes omite filas sin CUIT válido (11 dígitos y dígito verificador) para evitar crear clientes “huérfanos” sin identificación.
  - **Fusión de Duplicados**: Si existe un cliente sin CUIT y luego se importa el mismo cliente con CUIT, el sistema fusiona automáticamente referencias (registros, proyectos, contactos y puntajes) y elimina el duplicado sin CUIT.
- **Limpieza de Código**:
  - Se eliminaron scripts de prueba y validación (test_*.py, verify_*.py) para mantener el repositorio limpio.
  - Se eliminaron scripts de depuración (debug_*.py, fix_*.py, check_*.py) y archivos de vista previa temporales.
  - Se limpiaron archivos generados por Python (`__pycache__`, `*.pyc`) para evitar ruido en el workspace.
- **Mejoras en Visualización (Comercial)**:
  - **Tabla de Registros Unificada**: Se reemplazó la vista antigua de registros para el "Dpto Comercial" por la tabla de "Registros Detallados" del Dashboard Comercial, incluyendo ordenamiento automático descendente por ID de Trato.
  - **Coherencia en Dashboard**: Se corrigió el filtrado de tarjetas en el Dashboard Comercial para que coincida con los contadores de métricas, asegurando que proyectos sin fecha de cierre explícita (pero creados/actualizados en el periodo) aparezcan correctamente.
  - **Detalle de Tratos Mejorado**: Ahora al visualizar el detalle de un trato, se muestra información completa del contacto asociado, incluyendo email, teléfono y dirección, además de los datos básicos.
  - **Estabilidad en Generación de Roles (Nuevo Despliegue)**:
  - **Unificación de Lógica**: Se ha estandarizado la lógica de creación de roles en todo el sistema (`init_db`, `generate_roles_from_nomina`, `get_or_create_role_from_sector`). Ahora todas las vías utilizan la misma normalización estricta (snake_case) y mapeo de nombres.
  - **Prevención de Duplicados**: Se reforzaron las validaciones para evitar duplicados por mayúsculas/minúsculas (ej. `Adm_comercial` vs `adm_comercial`) o prefijos redundantes (`adm_adm_comercial`).
  - **Corrección de Configuración**: Se separaron las constantes de roles `ADM_COMERCIAL` y `DPTO_COMERCIAL` en la configuración del sistema para garantizar que se inicialicen como entidades distintas con sus permisos correctos desde el primer despliegue.
  - **Consistencia en Nómina**: La carga manual o por Excel de empleados ahora genera roles consistentes con la nomenclatura del sistema (ej. "Comercial" -> `dpto_comercial`, "Admin" -> `adm_administracion`), evitando la fragmentación de permisos.
- **UI (Ajustes)**:
  - **Logo sin Fullscreen**: Se deshabilitó el botón de fullscreen que aparecía al pasar el mouse sobre el logo (login y menú principal).

## 1.2.59
- **Departamentos – Inserción corregida**:
  - **Tipo booleano en is_hidden**: Al crear departamentos, `is_hidden` se guarda como `BOOLEAN` verdadero/falso en lugar de enteros `0/1`, evitando errores de tipo en PostgreSQL.
  - **Rol administrador asociado**: Se crea el rol administrador (`adm_<departamento>`) con `is_hidden = False` y `view_type` consistente (`admin_<view_type>`).
- **Dashboard sin vista asignada**:
  - **Mensaje de placeholder**: Para usuarios con departamentos sin vista configurada, se muestra “No hay vistas configuradas para este departamento” al iniciar sesión, dejando claro el estado pendiente de configuración.

## 1.2.58
- **Dashboard Comercial – Datos del Cliente en Tratos**:
  - **Tarjeta de Cliente enriquecida**: La tarjeta de “Datos del cliente” en “Crear Trato Comercial” ahora lee y muestra también CUIT, Celular y Web directamente desde la tabla de clientes, en lugar de dejarlos siempre como “-”.
  - **Clientes creados desde el propio trato**: Cuando se crea un cliente manualmente desde el flujo comercial, el cliente temporal guarda CUIT, Celular y Web en la tabla `clientes`, y la tarjeta los muestra inmediatamente junto con Teléfono y Email.
  - **Compatibilidad hacia atrás**: Los clientes creados antes de esta versión que no tenían CUIT/Celular almacenados seguirán viéndose con “-” en esos campos; los nuevos ya se visualizan completos.
- **Dashboard Comercial – Descripción de Tratos**:
  - **Contador simplificado**: Se eliminó el contador nativo “x/2000” en el campo de descripción de tratos comerciales (crear/editar), manteniendo internamente el límite de 2000 caracteres mediante lógica propia. Esto evita la confusión de que sea obligatorio llegar a 2000 caracteres, respetando a la vez el mínimo de 20 caracteres requerido para guardar.
- **Gestión de Clientes – Lista**:
  - **Columnas ocultas por defecto**: La vista “Lista” oculta las columnas `activo` e `id_cliente`.
  - **Limpieza automática de columnas vacías**: Columnas completamente vacías (valores vacíos/None) se ocultan por defecto para mejorar la legibilidad.
  - **Orden de columnas por defecto**: La tabla se muestra en el siguiente orden de prioridad: `CUIT`, `Nombre`, `Email`, `Teléfono`, `Celular`, `Web (URL)` y luego el resto de columnas disponibles.
 - **Dashboard Comercial – Pestaña “🏢 Clientes”**:
   - **Nueva pestaña**: El usuario Comercial dispone de una pestaña “Clientes” que muestra la misma tabla de clientes de la vista “Lista”, con las mismas reglas de visualización (oculta `activo` e `id_cliente`, oculta columnas vacías y orden preferente de columnas).
   - **Subpestañas**: La pestaña “Clientes” ahora incluye “Clientes” y “Marcas”. La subpestaña “Marcas” muestra la tabla de marcas con las mismas reglas de visualización (oculta `id_marca` y `activa`, oculta columnas vacías y orden por `CUIT`, `Nombre`, `Email`, `Teléfono`, `Celular`, `Web (URL)`).
 - **Dashboard Comercial – Navegación en tarjetas**:
   - **Tarjeta clickeable**: En el Dashboard Comercial (adm_comercial), la tarjeta completa del proyecto es clickeable y lleva al detalle del proyecto en la pestaña “Tratos Dpto Comercial”.
 - **Gestión de Marcas – Campos alineados con Clientes**:
   - **Nuevas columnas en Marcas**: Se añadieron `CUIT`, `Email`, `Teléfono`, `Celular` y `Web (URL)` a la tabla `marcas`, manteniendo `Nombre` y `Habilitada`.
   - **Agregar/Editar Marca**: Los formularios ahora permiten cargar y editar todos estos campos, con normalización de CUIT y corrección del protocolo en Web.
   - **Tabla de Marcas**: Oculta columnas vacías automáticamente y ordena por defecto como en Clientes: `CUIT`, `Nombre`, `Email`, `Teléfono`, `Celular`, `Web (URL)`.

## 1.2.57
- **Feriados (UX y Datos)**:
  - **Carga desde Excel simplificada**: Al seleccionar la hoja “Feriados”, se detectan automáticamente las columnas de Fecha, Nombre y Tipo. Nombre y Tipo son opcionales; si existen se utilizan, si no, se autogeneran (Nombre “Feriado dd/mm/aaaa”, Tipo “nacional”).
  - **Persistencia de sección**: En el panel de Visor/Hipervisor se reemplazaron las tabs principales por `segmented_control` para mantener la sección “Feriados” activa durante la subida y el procesamiento del Excel (evita saltos a “Visualización de Datos” tras el reload).
  - **Expander mejorado**: La carga masiva está en un expander replegado por defecto y ubicada al final de la vista.
  - **Tabla unificada**: La lista de feriados ahora se muestra como una tabla (`st.dataframe`) con columnas Fecha, Nombre, Tipo, Estado. Las acciones de Activar/Desactivar y Eliminar se realizan desde un selector de fila con botones dedicados.
  - **Limpieza de modelo y UI**: Se eliminó el campo “Jurisdicción” de feriados en el esquema y la interfaz.
  - **Formato y legibilidad**: Fechas en formato dd/mm/aaaa, capitalización de Tipo y nombre en negrita.
- **Planificación Semanal (Admin y Usuario)**:
  - **Marcado visual de Feriados**: Los días feriados se muestran como “Feriado” y se colorean en naranja (mismo estilo que “Vacaciones”) en las grillas semanales.
  - **Filtrado de filas**: Se ocultan automáticamente las filas de usuarios que solo tienen “Feriado” y “Sin asignar” en la semana seleccionada, manteniendo el foco en asignaciones relevantes.
  - **Persistencia de pestaña en Dashboard Técnico**: Se reemplazaron las tabs por `segmented_control` sincronizado con el parámetro `utab` para mantener la pestaña activa al navegar entre semanas; ya no vuelve a “📝 Nuevo Registro” al cambiar de semana en la planificación.
- **Gestión de Usuarios/Nómina**:
  - **Expander por defecto**: “Generar Usuarios desde Nómina” ahora está colapsado por defecto para reducir ruido visual al ingresar a la pantalla.
- **Gestión de Clientes**:
  - **Expander por defecto**: “Agregar Nuevo Cliente” ahora está colapsado por defecto. La carga masiva permanece replegada y al final de la vista, manteniendo la tabla como protagonista.
- **Gestión de Grupos**:
  - **Expander por defecto**: “Agregar Nuevo Grupo” ahora está colapsado por defecto, manteniendo el foco en la lista de grupos y sus acciones.

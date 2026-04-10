# Changelog

Todas las notas de versión y cambios importantes del sistema.

## 1.2.80
- **Panel de Administración (SMTP y Notificaciones)**
  - **Subsecciones dedicadas**: La configuración de notificaciones se reorganizó en vistas separadas para SMTP, políticas de envío y plantillas, manteniendo todo el control relacionado en un único apartado de administración.
  - **Políticas por evento**: Se agregó una configuración específica por tipo de notificación para definir si el correo está habilitado y con qué frecuencia se enviará (`inmediata`, `diaria` o `semanal`, según el evento).
  - **Control de horario y corte semanal**: Las políticas permiten fijar hora de envío y día de corte para resúmenes semanales, dejando preparada la base para evitar duplicados en futuros procesos automáticos.
  - **Evento de carga incompleta**: Se incorporó la estructura para “día pendiente de carga”, incluyendo política por defecto y plantilla de correo específica para resúmenes operativos.
- **Favoritos (Blindaje y UX)**
  - **Blindaje en técnico**: Se evitó el error al hacer clic rápido en el botón de favoritos cuando el selector de cliente aún no tiene valor (`int(None)`), deshabilitando el botón y validando el ID de forma segura.
  - **Ordenación con ⭐**: Los clientes favoritos del usuario técnico se priorizan al tope del selector, con indicador visual en el desplegable.
- **Favoritos en Comercial**
  - **Crear Trato Comercial**: El selector de cliente en “🆕 Nuevo Trato” incorpora la misma lógica de favoritos que el dashboard técnico (orden por favoritos y botón ⭐/☆ para marcar/desmarcar).
  - **Persistencia por usuario**: El marcado se guarda por usuario y afecta todos los selectores que lo implementan.
- **Solicitud de Clientes (Comercial)**
  - **Acceso desde pestaña “🏢 Clientes”**: Nuevo botón “Solicitar nuevo cliente” que abre el mismo modal de alta manual usado en “Nuevo Trato”.
  - **Creación consistente**: En el flujo estándar se crea el cliente temporal y la solicitud de aprobación vinculada. Si la solicitud fallara, se limpia el cliente temporal para evitar datos “huérfanos”.
  - **Robustez de notificaciones**: El encolado de eventos de notificación asegura el esquema de colas al vuelo y, si no pudiera encolar, no bloquea la creación de la solicitud.
  - **Esquema de solicitud más flexible**: Se ampliaron `telefono` y `celular` a `VARCHAR(50)` para admitir formatos reales de contacto.
- **Filtros de Tratos (Dpto Comercial)**
  - **Búsqueda por ID**: Se agregó un filtro “ID de trato” para ubicar rápidamente un trato por su número en “Tratos del Departamento Comercial”.

## 1.2.79
- **Panel de Administración (SMTP y Notificaciones)**
  - **Configuración SMTP segura**: Se agregó una sección dedicada para configurar envío por Gmail SMTP con contraseña de aplicación, validación de campos obligatorios, formato de email, puertos válidos y conservación segura de la contraseña ya guardada.
  - **Plantillas múltiples por evento**: La configuración de notificaciones ahora permite administrar una plantilla general y varias específicas según el tipo de evento, con fallback automático a la plantilla por defecto.
  - **Eventos iniciales preparados**: Se incorporaron plantillas base para solicitud de cliente creada, aprobada, rechazada, trato por vencer y trato vencido.
  - **Etiquetas visuales para variables**: Las variables disponibles de cada plantilla ahora se muestran como pills rosas, con tooltip al pasar el cursor para explicar cada etiqueta y con mejor espaciado visual en la interfaz.
  - **Persistencia unificada de plantillas**: Las plantillas de notificación se serializan y guardan en la configuración para mantener consistencia entre recargas del entorno.
- **Dashboard Comercial (Tratos)**
  - **Paginación ampliada**: La vista “Tratos del Departamento Comercial” ahora muestra 10 registros por página en lugar de 6.

## 1.2.78
- **Dashboard de Usuario (Planificación Semanal - Mobile)**
  - **Vista responsive mejorada**: Se reordenó el editor semanal para que cada día muestre título, fecha y selector en el mismo bloque, con mejor legibilidad en teléfonos.
  - **Columna `Usuario` fija y opaca**: Se reimplementó la grilla semanal para mantener la columna de nombres visible al desplazar y evitar superposición con las columnas de días.
  - **Compatibilidad con temas**: La columna fija ahora adapta fondo, texto y sombra al tema activo de Streamlit en light/dark.
  - **Tabla más usable en mobile**: Se ajustaron anchos, tipografías y scroll horizontal para que los encabezados y celdas entren mejor sin afectar escritorio.
  - **Alias de clientes en planificación**: Los desplegables y la tabla semanal muestran alias de clientes cuando existen, manteniendo el nombre real como dato persistido.
  - **Alcance controlado**: Los ajustes visuales se limitan a reglas responsive (`max-width: 768px`) para no alterar la experiencia desktop salvo mejoras puntuales de render.

## 1.2.77
- **Planificación Semanal (Carga de Planilla)**
  - **Validación integral de ausencias**: La importación ahora cruza usuarios detectados y rango semanal visible para omitir automáticamente días con feriados/licencias/vacaciones, incluyendo modalidades de ausencia ocultas.
  - **Asociación de usuarios más robusta**: Se mejoró el matching de la columna `Equipo` para reconocer variantes parciales y reducir asignaciones incorrectas o faltantes.
  - **Reporte de filas no vinculadas**: Si una fila no puede asociarse a un usuario existente, se informa explícitamente al finalizar la carga.
- **Planificación Semanal (Admin/Adm_Técnico y Técnico)**
  - **Propagación al cronograma habitual**: Se incorporó checkbox para que, al guardar la semana, también se actualice el cronograma por defecto del técnico sin reimportar planilla completa.
  - **Respeto de reglas de negocio**: La propagación omite días con feriados/licencias/vacaciones y evita sobrescribir asignaciones especiales.
  - **Sincronización de semanas futuras**: Al actualizar el cronograma habitual, también se alinean semanas futuras que seguían el patrón anterior.
  - **Consistencia visual tras guardar**: Se invalidan cachés de planificación, se sincroniza `rol_id` y el checkbox de propagación vuelve desmarcado automáticamente.
  - **Menor recarga en vista técnica**: La planificación semanal técnica se renderiza en fragmento para reducir recargas globales del dashboard durante la edición.
- **Dashboard de Usuario (Registros de Horas)**
  - **Favoritos y alias de clientes**: Se agregó marcado persistente por técnico, priorización en el listado, ícono `⭐` y visualización de alias cuando existe.
  - **Interacción más ágil**: Se añadió botón de favorito junto al selector y se encapsuló el formulario en fragmento para reducir recargas globales al seleccionar cliente.
- **Dashboard de Usuario (Planificación Semanal - Selector Cliente)**
  - **Selector unificado**: Se adoptó un selector de cliente de selección única con placeholder, manteniendo el estilo del resto del sistema.
  - **Limpieza de selección integrada**: Se habilitó limpieza directa desde el control (estilo nativo) para evitar acciones redundantes.
- **Dashboard Comercial (Registro de tratos)**
  - **Columna de marca visible y exportable**: Se incorporó la columna **Marca** en “Registros Detallados”, por lo que también queda incluida al exportar esa grilla.

## 1.2.76
- **Planificación Semanal (Tabla)**
  - **Columna fija de Usuario**: Se fijó la primera columna para que el nombre del usuario permanezca visible durante el desplazamiento horizontal en pantallas pequeñas en los paneles de Usuario, Admin y adm_tecnico.
  - **Fondo sólido en columna fija**: Se definió un fondo sólido adaptado al tema claro/oscuro para evitar que se transparenten las celdas desplazadas por detrás.
  - **Solape corregido al deslizar**: Se reforzó el apilado visual de la columna fija para impedir que el contenido de columnas desplazadas se vea por debajo.
  - **Paridad con vista técnica en Admin**: Se aplicó truncado con ellipsis y tooltip en celdas para evitar que nombres largos expandan columnas.
  - **Fijación robusta de columna en Admin**: Se aplicó clase fija sobre la columna real de Usuario para evitar fallas de sticky por estructura HTML y mantener ancho bloqueado.
  - **Compatibilidad del layout en tabla estilada**: Se apuntó el CSS al selector real del HTML generado para asegurar anchos fijos y sticky en Admin.
  - **Resumen “Hoy en la oficina” mejorado**: Se normalizó el nombre de cliente para reconocer variantes de Systemscorp y mostrar correctamente asignaciones del día.
  - **Error de variable local corregido**: Se eliminó el sombreado de `normalize_name` en Admin para restaurar el resumen de “Hoy en la oficina”.
  - **Carga de planilla sin pisar licencias**: Al aplicar la planilla a la semana visible, ahora se preservan asignaciones ya cargadas de licencia (`Vacaciones`, `Licencia`, `Dia de Cumpleaños`) y no se sobrescriben con modalidades de cronograma.
- **Clientes y Contactos (Validación de Teléfono)**
  - **Teléfonos del interior habilitados**: Se flexibilizó la validación para aceptar números del interior y formatos diversos (no solo variantes de 011), manteniendo controles básicos de longitud y caracteres permitidos.
- **Acceso y Seguridad**
  - **Registro público deshabilitado**: Se eliminó la pestaña “Registrarse” del login para que la creación de usuarios se haga únicamente desde el panel de Administración.

## 1.2.75
- **Registros (Validación de Horas)**
  - **Tope por registro**: Se bloquea el guardado si un registro individual supera 24 horas.
  - **Tope diario acumulado**: Se bloquea el guardado/edición cuando la suma de horas del técnico en una misma fecha supera 24 horas (por ejemplo, 3h + 22h el mismo día).

## 1.2.74
- **Registros (Fechas)**
  - **Corrección de inversión día/mes**: Se ajustó el parseo central de fechas para priorizar el formato ISO (`YYYY-MM-DD`) antes de formatos `DD/MM/YY` y `DD/MM/YYYY`, evitando que fechas editadas (ej. 06/03) reaparezcan como 03/06 al recargar.
  - **Consistencia en recarga**: Se garantizó que los registros editados mantengan la fecha correcta en el detalle, selector de edición y visualizaciones semanales tras guardar y refrescar.
- **Dashboard de Usuario (UX de Formulario)**
  - **Desplegables de alta vacíos por defecto**: Cliente, Tipo de Tarea y Modalidad ahora inician sin valor preseleccionado para permitir búsqueda directa sin borrar manualmente.
  - **Reset post-guardado**: Se reforzó la limpieza automática del formulario de nuevo registro luego de guardar, sin requerir recarga manual de página.
  - **Refresco tras edición**: Se agregó rerender automático al guardar cambios en edición de registros para evitar estado visual desactualizado.
- **Planificación Semanal (Tabla)**
  - **Anchos fijos reales por columna**: Se endureció el layout para impedir expansión horizontal por textos largos.
  - **Truncado visual con tooltip**: Las celdas muestran puntos suspensivos cuando exceden ancho y conservan el valor completo en tooltip al pasar el cursor.

## 1.2.73
- **Gestión de Marcas (Admin)**:
  - **Corrección de Actualización**: Se amplió el límite de caracteres para los campos `celular` (50 chars) y `telefono` (100 chars) en la base de datos para evitar errores al guardar números largos.
  - **Manejo de Errores**: Se mejoró la respuesta de error al actualizar marcas, mostrando mensajes específicos (ej. duplicados, longitud excedida) en lugar de un error genérico.
  - **Consistencia de Datos**: Se corrigió el guardado de campos opcionales vacíos (`""`) para que se almacenen como `NULL` en la base de datos, manteniendo la consistencia visual ("None") con el resto de registros.
- **Dashboard de Usuario (UX)**:
  - **Notificaciones de Carga**: Se implementó un sistema de alertas que notifica al usuario técnico mediante un icono en la cabecera y notificaciones tipo "toast" si tiene días laborables (lun-vie) en el mes actual con menos de 4 horas registradas, excluyendo feriados.
- **Correcciones de Estilo (UI)**:
  - **Conflicto de Tema Oscuro**: Se eliminaron las reglas CSS que forzaban estilos de "Modo Claro" basados en la preferencia del sistema operativo, solucionando el error donde las tarjetas se veían blancas (ilegibles) cuando el usuario seleccionaba "Dark Mode" en la aplicación pero tenía su sistema en "Light Mode".

## 1.2.72
- **Backup y Restauración**:
  - **Manejo de NaT/NaN**: Se mejoró la robustez del proceso de restauración de backups para manejar correctamente valores de fecha nulos (`NaT`, `NaN`, `nan`) provenientes de Excel, evitando errores de sintaxis SQL (`invalid input syntax for type timestamp: 'NaT'`).
- **Panel de Administración (UX)**:
  - **Persistencia de Pestañas**: Se reemplazó el sistema de navegación por pestañas (`st.tabs`) en la sección de Administración por controles segmentados (`st.segmented_control`) con estado persistente. Esto evita que la vista se reinicie a la primera pestaña ("Conexiones") al interactuar con elementos que recargan la página, como la subida de archivos de backup.

## 1.2.71
- **Backup y Restauración**:
  - **Corrección de fechas**: Se solucionó un error crítico al restaurar backups donde fechas vacías (exportadas como "NaT") causaban fallos de sintaxis en la base de datos.

## 1.2.70
- **Gestión de Clientes**:
  - **Corrección de eliminación**: Se solucionó un error que impedía eliminar clientes debido a una columna faltante (`temp_cliente_id`) en la tabla de solicitudes temporales.

## 1.2.69
- **Sidebar (Perfil)**:
  - **Textos largos**: Nombre/Apellido/Correo ahora cortan línea correctamente (emails largos) y muestran tooltip con el valor completo.
- **Validaciones (Formularios)**:
  - **Alta Contacto**: El campo "Teléfono" ahora es obligatorio en todos los formularios de creación, edición e importación masiva.
  - **Alta Cliente**: El campo "Web (URL)" ahora es obligatorio en los formularios de creación, edición, solicitudes comerciales e importación masiva.
- **Carga de Registros (Técnicos)**:
  - **Campos obligatorios**: Ahora "Tarea Realizada" y "Descripción" son obligatorios al crear o editar registros manuales. "Número de Ticket" permanece opcional.

## 1.2.68
- **Modalidades (UX)**:
  - **Eliminación sin refresh manual**: Al eliminar una modalidad, la pantalla se actualiza automáticamente, limpiando selecciones y evitando que siga apareciendo hasta recargar el navegador.
- **Grupos (Gestión)**:
  - **Eliminación con dependencias**: Al eliminar un grupo, el sistema elimina primero sus asociaciones/puntajes (ej. `grupos_roles`, `grupos_puntajes`) para evitar errores de clave foránea.

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

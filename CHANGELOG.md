# Changelog

Todas las notas de versión y cambios importantes del sistema.

## 1.2.97
- **Backup y Restauración (JSON)**
  - **Normalización de JSON/JSONB**: Se agregó lógica para manejar correctamente campos JSON/JSONB tanto al crear backups como al restaurarlos.
  - **Compatibilidad con backups antiguos**: Incluso si el backup tiene JSON con comillas simples (formato dict de Python), el sistema lo convierte automáticamente a JSON válido con comillas dobles.
  - **Serialización correcta en backups**: Al crear nuevos backups, las columnas JSON/JSONB se serializan correctamente como strings JSON con comillas dobles.
- **Licencias (Flujo y Rendimiento)**
  - **Navegación por secciones internas**: La pestaña `🌴 Licencias` de `Adm. Técnico` pasó de `st.tabs` a un selector de secciones que renderiza solo la parte activa, evitando cargar contenido de otras vistas y la “sombra” del Dashboard Comercial mientras sigue corriendo el render.
  - **Mensajes no bloqueantes**: Aprobar/rechazar una solicitud de licencia ya no usa `time.sleep` ni reruns manuales dentro del submit; los avisos se muestran mediante notices no bloqueantes en `st.session_state`.
  - **Trazabilidad de aprobación**: Se conserva y muestra `reviewed_by`, `reviewed_at` y `review_comment` tanto en la UI de solicitudes como en los correos de notificación.
  - **Reads más rápidos**: Se eliminaron llamadas DDL (`ensure_*_schema`) de los paths de lectura de solicitudes pendientes, balances y próximas licencias para acelerar el render inicial del visor.
  - **Optimización de alertas técnicas**: `get_technical_alerts_data()` ahora precarga feriados una vez y usa un mapa de horas por fecha, reduciendo el tiempo de carga del panel.
- **Google Calendar (OAuth)**
  - **Corrección de state mismatch**: El `state` de OAuth ya no se regenera en cada rerun de Streamlit. Se cachea en `st.session_state` y se reutiliza mientras siga siendo válido, evitando el error “el parámetro de estado (state) de OAuth no coincide” durante la vinculación.
  - **Notices post-callback**: Los resultados del callback de Google (éxito/error) se guardan en un aviso persistente y se muestran inmediatamente al volver a la vista de Google Calendar, sin time.sleep que prolongue la carga.
- **Módulo Comercial y Cotización Técnica**
  - **Nomenclatura**: `Cotizaciones` pasa a llamarse `Solicitar Costo` y `Informe Técnico` a `Cotización Técnica` en menús, títulos, botones y notificaciones.
  - **Orden del menú Comercial**: Se reordenaron las opciones en `Nuevo trato`, `Mis tratos`, `Costos`, `Cotización técnica`, `Clientes`, `Contactos`, `Compartidos conmigo`.
  - **Nueva Solicitud de Costo**: Se eliminaron `Teléfono` y `Contacto` de los datos generales; el botón principal comparte estilo con `Agregar Contacto`; el botón `Guardar` pasa a `Enviar` y todos los botones de la pantalla quedan con tamaño y espaciado uniformes.
  - **Importación Excel**: Ya no cierra el formulario al importar; se mantiene abierto para revisar y editar. La columna `Precio` se quitó del template y del importador.
  - **Validaciones de importación**: `Cantidad` acepta solo enteros positivos y ya no se reemplaza silenciosamente por “1”; los errores informan fila, columna y motivo.
  - **Cards de Cotización**: Se rediseñaron para ser más compactas, eliminando información redundante respecto a la cabecera y facilitando el seguimiento cuando hay múltiples registros.
  - **Detalle del Trato**: `Nueva serie` y `Ver informe` pasan a `Solicitar cotización técnica` y `Solicitar costos`; en archivos solo se muestran los adjuntos vigentes.
  - **Comentarios de Cotización Técnica**: Se usa un contenedor de altura fija con scroll vertical, al estilo de `Cotizaciones`, manteniendo remitente, fecha, hora y comentario sin extender la pantalla indefinidamente.
  - **Notificaciones para Técnico**: El dashboard de `Adm. Técnico` ahora muestra alertas para `Cotización Técnica` pendientes.
  - **Archivo vigente en Cotización Técnica**: Se corrigió la identificación del último archivo como vigente, el cambio se persiste correctamente y desapareció el falso mensaje de “No hay cambios para guardar”.

## 1.2.96
- **Informes técnicos (Nuevo flujo operativo)**
  - **Nueva gestión por trato**: Se incorporó el módulo de `Informe técnico`, asociado de forma permanente a cada trato y disponible mientras el trato permanezca abierto.
  - **Pestañas por rol**: `comercial` ahora cuenta con la pestaña `Informe técnico` para solicitar y seguir informes, y `adm_tecnico` suma `Seguimiento informe` para responderlos.
  - **Acceso desde el trato y dashboard**: El informe puede abrirse tanto desde el botón del trato como desde el workspace dedicado de informes.
- **Informes técnicos (UX y visual)**
  - **Workspace con tarjetas**: La vista principal pasó a un esquema de tarjetas clickeables, filtros y apertura directa del informe, alineado con la experiencia de `Cotizaciones`.
  - **Carga más liviana**: Se optimizó la carga inicial y la apertura del detalle con consultas cacheadas para informes, comentarios, documentos y tratos visibles.
  - **Detalle unificado**: El encabezado, los comentarios y la sección de documentos adoptaron una presentación consistente con `Cotizaciones`, incluyendo documento vigente destacado, selector de descarga y bloques visuales más claros.
  - **Solicitud como título**: El texto inicial del pedido ahora funciona como `Título de la solicitud`, se muestra como cabecera principal del informe y deja de editarse una vez creado.
- **Informes técnicos (Estados y notificaciones)**
  - **Estado propio del informe**: Las tarjetas y el detalle usan estados específicos del informe técnico: `Solicitado` cuando comercial genera o actualiza el pedido y `Enviado` cuando responde `adm_tecnico`.
  - **Eventos de aviso**: Se agregaron eventos y políticas de notificación para `Informe técnico solicitado` e `Informe técnico actualizado`.
- **Cotizaciones (Comentarios de solicitud)**
  - **Un solo comentario por pedido**: Al solicitar una cotización o una nueva versión, el sistema ahora guarda únicamente el comentario escrito por el usuario.
  - **Fallback automático**: Si el campo comentario queda vacío, se registra un mensaje por defecto para evitar comentarios redundantes o duplicados.

## 1.2.95
- **Cotizaciones (Ciclo de vida y permisos)**
  - **Cierre automático por trato**: Las cotizaciones vinculadas a un trato que pasa a estado final se cierran automáticamente y quedan bloqueadas para preservar historial.
  - **Asignación por persona**: La solicitud de cotización ahora permite elegir destinatario específico entre perfiles habilitados, y cada usuario ve solo las cotizaciones asignadas.
  - **Bandeja operativa para administración comercial**: `adm_comercial` suma una pestaña `Compras` con capacidad operativa sobre cotizaciones asignadas, manteniendo restricciones de borrado en ese contexto.
  - **Documento vigente controlado por Comercial**: La selección del documento vigente pasa a `comercial` / `adm_comercial`; la primera respuesta de Compras queda marcada por defecto cuando aún no existe un vigente.
  - **Reapertura explícita**: Una cotización cerrada manualmente ahora muestra acción `Reabrir` en el botón principal, manteniendo consistencia visual y evitando combinaciones ambiguas con `Solicitar nueva version`.
- **Cotizaciones (Series, marca y UX)**
  - **Series paralelas por trato**: Un mismo trato puede tener múltiples series de cotización independientes (`1`, `2`, `3`, etc.), cada una con sus propias iteraciones documentales (`1a`, `1b`, `2a`, ...).
  - **Marca por serie**: La cotización incorpora selección de `Marca` editable solo por `comercial` / `adm_comercial`, lo que permite manejar alternativas paralelas dentro del mismo trato.
  - **Tarjetas por serie en el detalle del trato**: El apartado de cotizaciones dentro del trato ahora muestra una tarjeta independiente por serie, con datos clave visibles y acceso directo a abrir o descargar la versión vigente.
  - **Importación más clara**: La carga de ítems desde Excel quedó detrás de un checkbox dedicado, se eliminó el botón redundante de importación y `Exportar Excel` solo se habilita cuando existen ítems reales cargados.
- **Notificaciones y navegación**
  - **Título de pestaña dinámico**: La app usa `SIGO` como título del navegador e incorpora contador de notificaciones no vistas en la pestaña.
  - **Conteo agregado por categoría**: Las alertas de cotizaciones y de Compras se cuentan como una sola notificación por categoría, sin inflarse por la cantidad de registros subyacentes.
  - **Toasts diarios**: Las notificaciones visuales emergentes se muestran una sola vez por día y por usuario, mientras la campana conserva el detalle pendiente hasta su revisión.
  - **Ingreso limpio a Compras**: Se corrigió la apertura automática involuntaria de cotizaciones al cambiar a la pestaña `Compras` en `adm_comercial`, manteniendo la apertura normal al hacer clic en una tarjeta.
- **Eliminación y limpieza de archivos**
  - **Confirmación al eliminar tratos**: El borrado de un trato ahora solicita confirmación explícita antes de ejecutar la acción.
  - **Limpieza física de adjuntos**: Al eliminar un trato se borran también los documentos físicos del trato, los archivos de cotizaciones asociadas y las carpetas vacías residuales dentro del árbol de uploads.

## 1.2.94
- **Cotizaciones (Excel y documentos)**
  - **Plantilla con precio**: La exportación de ítems de cotización y el `Template Excel` ahora incluyen la columna `precio` para que Compras pueda completar el valor sobre la misma planilla.
  - **Vigente más visible**: El documento marcado como vigente se destaca visualmente antes del selector de descarga para facilitar su identificación.

## 1.2.93
- **Cotizaciones (Versionado)**
  - **Nueva versión sobre la misma cotización**: Comercial y adm_comercial ahora pueden volver a solicitar una nueva versión a compras sin perder el historial previo.
  - **Historial preservado**: Los documentos adjuntos se mantienen sobre la misma cotización y se muestran como `Version 1`, `Version 2`, etc., conservando cuál queda marcada como vigente.
  - **Re-solicitud a compras**: La acción `Solicitar nueva version` vuelve el pedido a estado `Solicitado` y reenvía la solicitud al sector compras.

## 1.2.92
- **Cotizaciones (Comercial / Adm. Comercial / Compras)**
  - **Entidad propia**: Las cotizaciones ahora se gestionan con tablas propias, asociadas a un trato comercial.
  - **Nueva pestaña final**: Se agregó `Cotizaciones` al final de las vistas de `comercial` y `adm_comercial`, con filtros por trato, CUIT, razon social y estado.
  - **Solicitud y administracion**: Comercial y administracion comercial pueden crear y gestionar cotizaciones vinculadas a los tratos que tienen visibles; `adm_comercial` puede operar sobre todos los tratos abiertos del sector.
  - **Recepcion en compras**: Las solicitudes nuevas se notifican al rol `compras`, que ahora consulta y gestiona las cotizaciones recibidas desde su propio panel.
  - **Detalle operativo**: Cada cotizacion soporta items, comentarios historicos, documentos adjuntos y marcado de documento vigente.

## 1.2.91
- **Compras**
  - **Nuevo rol del sistema**: Se agregó el rol `compras` con navegación propia para consulta de cotizaciones.
  - **Pestaña Cotizaciones**: El nuevo panel permite filtrar cotizaciones por `id`, `CUIT`, razón social y estado, además de exportar el resultado filtrado.
  - **Consulta de detalle**: Desde la vista de compras se puede abrir el detalle de cada cotización y descargar sus documentos adjuntos en modo solo lectura.
- **Cotizaciones (Listado y filtros)**
  - **Workspace unificado**: La gestión de cotizaciones pasó a un esquema de tarjetas con filtros por trato, cliente, marca, nombre del proyecto y estado, alineado con la experiencia visual de `Tratos`.
  - **Exportación total en Excel**: Se agregó `Exportar todo` en formato `.xlsx`, respetando filtros activos y excluyendo la columna `Acciones`.
  - **Vista de Compras ampliada**: El perfil `compras` suma filtro por `Vendedor` y ordenamiento por fecha de solicitud (`Más recientes`, `Ascendente`, `Descendente`).
- **Cotizaciones (Editor y UX)**
  - **Editor de ítems estable**: Se reemplazó la grilla inestable por un editor nativo con fila vacía automática, scroll interno y exportación/importación Excel.
  - **Validación de cantidad**: El campo `Cantidad` quedó restringido a enteros positivos, evitando letras y normalizando valores inválidos.
  - **Comentarios y adjuntos escalables**: Los comentarios y documentos se muestran en contenedores más compactos, con mejor uso del ancho disponible y scroll interno discreto.
  - **Documento vigente destacado**: El documento marcado como vigente ahora se resalta visualmente en una tarjeta específica antes de la zona de descarga.
- **Cotizaciones (Trato y creación)**
  - **Apartado en detalle del trato**: Cada trato muestra su bloque de `Cotización` al final, permitiendo ver, descargar o solicitar cotización según corresponda.
  - **Botones simétricos**: Las acciones de `Ver cotización` y `Descargar cotización` quedaron visualmente alineadas y consistentes.
  - **Cotización embebida en Crear trato**: El alta de trato ahora permite `No cargar ahora`, `Cargar cotización` o `Solicitar a compras` desde un bloque embebido que crea la cotización asociada al guardar.
  - **Carga desde Excel**: Al elegir `Cargar cotización`, el archivo `.xls/.xlsx` se usa para poblar automáticamente los ítems de la cotización.
- **Cotizaciones (Permisos por rol)**
  - **Comercial y adm_comercial**: Ya no pueden adjuntar cotizaciones manualmente dentro del formulario de edición; sólo pueden comentar, revisar y solicitar nueva versión.
  - **Compras con ítems en solo lectura**: En el diálogo de `Compras`, la grilla de ítems se muestra sin edición y sólo conserva la opción `Exportar Excel`.
  - **Carga acotada de cotización**: El selector `Adjuntar cotización` quedó restringido a archivos Excel (`.xlsx` y `.xls`).
- **Cotizaciones (Estados y notificaciones)**
  - **Estado re-solicitado visible**: Al pedir una nueva versión, la cotización vuelve a `Solicitado`, y al responder `Compras` regresa a `Enviado`.
  - **Notificaciones por correo**: Se incorporaron eventos para avisar a `Compras` cuando entra una solicitud y al solicitante cuando `Compras` envía la cotización.
  - **Notificaciones visuales en la app**: Se agregaron campanas y `toast` para `Compras`, `Comercial` y `adm_comercial` según el estado de las cotizaciones.
  - **Persistencia de alertas vistas**: Las alertas visuales de cotizaciones enviadas quedan registradas en base de datos para mostrarse una sola vez por envío y no reaparecer tras cerrar la app.

## 1.2.90
- **Registros (Usuario)**
  - **Orden por ID descendente**: En los selectores de editar y eliminar registros del dashboard de usuario, los registros ahora se muestran de mayor a menor `id`.

## 1.2.89
- **Visualizaciones (Horas por Usuario)**
  - **Mejor legibilidad**: Se aumentó levemente el tamaño de fuente de las etiquetas del eje X manteniendo nombres horizontales (Nombre/Apellido en dos líneas).

## 1.2.88
- **Notificaciones (Configuración)**
  - **Refactor de configuración**: Las definiciones de notificaciones (plantillas/políticas) se movieron a un módulo dedicado para mejorar mantenibilidad y reducir acoplamiento.
- **Notificaciones (Políticas: UX y rendimiento)**
  - **Guardado como única acción**: La selección de roles/usuarios se realiza dentro del formulario para evitar recargas por cada etiqueta; los cambios se aplican al presionar “Guardar política”.
  - **Orden de campos**: “Aplicar a” se mantiene arriba y el selector de Roles/Usuarios aparece inmediatamente debajo.
  - **Carga más rápida**: Roles/usuarios se consultan solo cuando corresponde y se cachean brevemente para acelerar el cambio de “Aplicar a”.

## 1.2.87
- **Notificaciones (Políticas: Alcance)**
  - **Targeting configurable**: Las políticas ahora permiten definir a quiénes aplican: **Todos**, **Rol(es)** específicos o **Usuario(s)** específicos.
  - **UI mejorada**: El alcance se elige en un desplegable (Todos / Rol / Usuario) y luego se seleccionan destinatarios con etiquetas (chips).
- **Notificaciones (Nuevos eventos)**
  - **Hoy en la oficina**: Nuevo evento diario que envía un resumen de quiénes están presentes hoy (según planificación semanal) e incluye un apartado opcional de licencias/vacaciones/cumpleaños de la semana cuando corresponda.
  - **Técnicos con carga incompleta (supervisión)**: Nuevo evento para supervisores con resumen y detalle de técnicos que presentan jornadas con carga incompleta en el período, configurable por política.
- **Notificaciones (Rendimiento)**
  - **Envío no bloqueante**: El procesamiento automático de notificaciones se ejecuta en segundo plano y aplica un presupuesto por corrida (límite de tiempo y cantidad de correos) para evitar congelar la app durante envíos masivos.
- **Notificaciones (Correcciones)**
  - **Sin hardcodeo por rol**: La selección de destinatarios se rige por el alcance configurado en la política, evitando exclusiones implícitas por `view_type`.

## 1.2.86
- **Registros (Fechas)**
  - **Formato persistido unificado**: `registros.fecha` se normaliza y guarda en formato ISO `YYYY-MM-DD`.
  - **Lectura consistente**: Se unificó el parseo de fechas de registros para listados, filtros, edición y validaciones, contemplando ISO y formatos legacy `DD/MM/YYYY`.
  - **Validaciones alineadas**: La detección de duplicados y el control de horas por día comparan fechas normalizadas para evitar cruces por formato.
- **Backup y Restore (Excel)**
  - **Exportación inequívoca**: Los backups completos vuelcan `fecha` como `YYYY-MM-DD` y los timestamps `*_at` como `YYYY-MM-DD HH:MM:SS`.
  - **Restore normalizado**: La restauración convierte `registros.fecha` al formato ISO antes de insertar.
  - **Refresco post-restore**: Se limpian cachés de registros y gráficos al finalizar una restauración exitosa.
- **Registros (Admin y Técnico)**
  - **Edición admin corregida**: Se reparó el formulario de edición para administradores, usando las columnas reales de `registros`, actualizando `mes` al cambiar `fecha` y persistiendo correctamente el registro editado.
  - **Estado estable en edición/eliminación admin**: La gestión individual de registros en admin ahora conserva el registro seleccionado entre reruns de Streamlit, evitando pérdidas de contexto al editar o eliminar.
  - **Altas automáticas consistentes**: Las altas automáticas asociadas a vacaciones/licencias también pasan a guardar `fecha` en ISO para no reintroducir mezclas de formato.

## 1.2.85
- **Planificación Semanal (Modalidad)**
  - **Grilla completa en semanas futuras**: La vista del equipo ahora completa asignaciones usando el **cronograma habitual** cuando la semana seleccionada no tiene asignaciones guardadas, evitando que se oculten usuarios por quedar “Sin asignar”.
  - **Consistencia visual**: Se mantiene el criterio de mostrar usuarios con al menos una asignación efectiva (por ejemplo, si un usuario tiene un día asignado en la semana, se muestra aunque el resto esté sin asignar).
- **Solicitud de Clientes (Comercial)**
  - **Modal estable entre pestañas**: Se corrigió la reapertura involuntaria del modal “Cargar cliente” al cerrar con X y cambiar entre “🏢 Clientes” y “🆕 Nuevo Trato”.
  - **Transición inmediata a formulario**: El paso “Crear nuevo cliente” ahora navega al formulario de solicitud en un solo click.
  - **Crear cliente desde Nuevo Trato**: Se evitó un loop de recarga cuando el selector está en “➕ Crear nuevo cliente”, permitiendo que el formulario se muestre correctamente.
  - **Sin rerun en callbacks**: Se eliminó la llamada a rerun dentro del callback del selector para evitar el mensaje “Calling st.rerun() within a callback is a no-op.” y asegurar un comportamiento consistente.
- **Registros (Edición y Exportación)**
  - **Sincronización de usuario al editar**: Al editar un registro y cambiar el técnico, ahora se actualiza también el `usuario_id` asociado para evitar cruces de horas entre usuarios.
  - **Reparación automática one-shot**: Se agregó un mantenimiento de única ejecución que re-sincroniza `usuario_id` de registros existentes según el técnico asociado, corrigiendo cruces históricos que afectaban visualización y exportes.

## 1.2.84
- **Planificación Semanal (Usuarios)**
  - **Ocultar usuarios deshabilitados**: Los usuarios con `is_active = FALSE` ya no se muestran en las vistas basadas en departamento/rol (por ejemplo, grillas de planificación).
  - **Refresco inmediato tras cambios**: Al activar/desactivar o eliminar un usuario desde el panel de administración, se invalidan las cachés de planificación para que el cambio impacte al instante.

## 1.2.83
- **Mantenimiento de Datos (Técnicos)**
  - **Unificación de técnicos legacy**: Se incorporó una rutina de mantenimiento que migra registros asociados a técnicos con nombre “corto” hacia el técnico canónico con nombre completo.
  - **Ejecución única en BD**: La rutina se ejecuta solo una vez (persistiendo un flag en base de datos y usando advisory lock), evitando reprocesos innecesarios en futuros inicios de sesión.
- **Dashboard Comercial (Paginación)**
  - **Selector de tarjetas por página**: Se agregó un selector (5–100) para definir cuántas tarjetas mostrar en **Tratos** y **Contactos** (roles `comercial` y `adm_comercial`).
  - **Integrado a la barra de paginación**: El selector se ubica junto al texto “Mostrando elementos x-x de x” y al cambiar el valor se reinicia a la página 1.

## 1.2.82
- **Dashboard Comercial (Montos)**
  - **Montos segregados**: Se reemplazó “Monto Total” por métricas separadas de **Monto Proyectado** y **Monto Ganado** en ARS/USD, respetando el filtro de fecha seleccionado.
  - **Criterio de proyección**: El monto proyectado considera tratos en curso cuya **fecha de cierre** cae dentro del período (referencia de cobro).
- **Panel de Visor (Carga incompleta)**
  - **Feriados excluidos**: El cálculo de “días con carga incompleta” ahora ignora feriados, alineándose con la alerta que ve el usuario técnico.

## 1.2.81
- **Backup (Excel)**
  - **Fechas consistentes**: Las columnas de fecha (`fecha` y `fecha_*`) se exportan como fechas reales con formato `DD/MM/YYYY`, evitando mezclas entre texto ISO (`YYYY-MM-DD`) y fechas formateadas.
  - **Timestamps consistentes**: Las columnas tipo timestamp (`*_at`) se exportan como datetime con formato `DD/MM/YYYY HH:MM:SS`.
  - **Columna `mes` normalizada**: El campo `mes` se exporta de forma homogénea como número (1–12) aunque internamente venga como nombre (“Marzo”, “Abril”, etc.).
- **Registros (Filtros y Fechas)**
  - **Período de tiempo robusto**: El filtro por rango de fechas interpreta correctamente `fecha` en formato ISO (`YYYY-MM-DD`), `DD/MM/YYYY` y `DD/MM/YY`, con fallback a `created_at` si el campo viene vacío o inválido.
  - **Prevención de fechas fuera de rango**: En formularios de carga/edición de registros se limita la selección de fecha para evitar años incoherentes (ej. 2015) por error de carga.
- **Registros (Técnico)**
  - **Descripción opcional**: El campo “Descripción” dejó de ser obligatorio al crear/editar registros de horas para usuarios técnicos.
- **Usuarios (Email)**
  - **Campo Email en ABM**: Se agregó el campo `email` en “Crear Usuario” y “Editar Usuario”, permitiendo cargar/actualizar el correo desde el panel de administración.
  - **Listado con Email**: La tabla de “Usuarios Existentes” ahora incluye la columna `Email`.
- **Tratos (Filtros)**
  - **Filtro por Marca**: Se agregó la posibilidad de filtrar tratos por `Marca` en las vistas de Comercial (“Mis Tratos” y “Tratos Compartidos Conmigo”) y en Admin Comercial (“Tratos del Departamento Comercial”).
- **Tratos (Contador de días)**
  - **Detención en estados finales**: El contador de días deja de mostrarse/calcularse cuando el trato está resuelto como `Ganado` o `Perdido`, incluyendo variantes de texto del estado.

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

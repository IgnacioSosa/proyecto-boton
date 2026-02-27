# Changelog

Todas las notas de versión y cambios importantes del sistema.

## 1.2.64
- **Corrección de Errores de Importación (Excel)**:
  - **Filas Vacías**: Se ignora automáticamente filas vacías al final del archivo para evitar errores de validación "Falta 'Trato - ID'".
  - **Sincronización de IDs**: Se corrige la incongruencia entre IDs de Excel (ej. 4537) y IDs de sistema (ej. 99923) al actualizar registros existentes, asegurando que se respete el ID original del archivo.
  - **Datos Completos**: Se asegura la carga de todos los campos del registro (incluyendo contacto, fecha, etc.) al importar.
- **Gestión Inteligente de Contactos**:
  - **Asignación Automática**: Se asignan automáticamente contactos existentes en el sistema a los registros importados del Excel 
  - **Búsqueda Difusa de Clientes**: Se implementó lógica de coincidencia difusa para vincular contactos cuando el nombre del cliente varía ligeramente 
- **Mejoras en Dashboard Comercial y Técnico**:
  - **Filtrado de Fechas**: Se corrigió la visualización de proyectos ganados/perdidos vencidos hace más de un año; ahora el filtro "Mes Actual" prioriza la fecha de cierre del negocio sobre la fecha de actualización del sistema.
  - **Visualización de Tarjetas (UI/UX)**:
    - **Optimización de Espacio**: Se redujo el tamaño de fuente de los títulos (de 22px a 18px) y se ajustó el truncado automático de textos largos (Títulos > 30 caracteres, Clientes > 20 caracteres) para evitar desbordamientos en tarjetas de proyecto.
    - **Tooltips**: Los textos truncados muestran su contenido completo al pasar el cursor (hover).
  - **Corrección de Métricas Técnicas**: Se solucionó el error donde la pestaña "Dpto Tecnico" no mostraba datos a pesar de existir registros cargados, asegurando la correcta conversión de tipos de datos en los filtros de roles.


## 1.2.63
- **Perfil de Usuario (Sidebar)**:
  - **Visualización Solo Lectura**: Se rediseñó la sección "Datos Personales" en la barra lateral. Ahora los campos (Nombre, Apellido, Email) se muestran en tarjetas informativas de solo lectura, eliminando la apariencia de formulario editable.
  - **Seguridad y Usabilidad**: El botón de acción se ha movido dentro del bloque "Cambiar Contraseña" y se ha renombrado a **"Actualizar Contraseña"**. Esto clarifica que la acción es exclusiva para la clave y previene confusiones sobre la edición de datos personales.

## 1.2.62
- **Gestión de Contactos (Selección y Persistencia)**:
  - **Restauración de Selección por URL**: Se reactivó la capacidad de seleccionar contactos mediante parámetros URL (`contactid`), permitiendo compartir enlaces directos a tarjetas específicas.
  - **Corrección de "Persistencia Pegajosa"**: Se implementó una limpieza automática del parámetro URL tras la carga inicial. Esto soluciona el problema donde un contacto cerrado volvía a abrirse automáticamente al recargar la página o cambiar de pestaña.
  - **Gestión Inteligente de Diálogos**: El modal de contacto ahora distingue entre interacciones activas (editar, guardar, favorito) y cierres explícitos, garantizando que solo se mantenga abierto cuando el usuario está interactuando con él.
- **Normalización de Datos (Contactos)**:
  - **Apellidos Opcionales**: Los contactos sin apellido ahora se guardan con una cadena vacía en lugar de "Sin dato", mejorando la visualización en las tarjetas (ej. "Pablo" en lugar de "Pablo Sin Dato").
  - **Limpieza Histórica**: Se ejecutó una normalización en la base de datos para limpiar los registros existentes que tenían "Sin dato" en el campo apellido.
  - **Campos "Sin dato" Automáticos**: En la creación manual y masiva, campos no obligatorios como Puesto, Email y Teléfono se rellenan automáticamente con "Sin dato" si se dejan vacíos, facilitando la carga rápida.
- **Carga Masiva de Contactos**:
  - **Mejora en Coincidencia de Organizaciones**: Se implementó una búsqueda difusa y normalizada (ignorando acentos, mayúsculas y caracteres especiales) para vincular contactos con Clientes o Marcas. Esto resuelve errores de importación con nombres complejos (ej. variaciones de "L'OREAL", "S.A.", o comillas).
  - **Bloqueo de Interfaz**: El botón de "Procesar Carga" se bloquea visualmente durante la ejecución para prevenir envíos múltiples accidentales.
- **Gestión de Clientes**:
  - **Campo Celular Opcional**: Se eliminó la obligatoriedad del campo "Celular" en los formularios de creación de clientes, tanto en el flujo comercial (Tratos) como en el panel de administración.

## 1.2.61
- **Dashboard Comercial – Métricas por Vendedor**:
  - **Colores por vendedor en gráficos de barras**: Los gráficos de “Tratos por Vendedor” y “Monto por Vendedor” utilizan ahora un color distinto por vendedor con leyenda visible, facilitando la comparación visual entre personas.
- **Dashboard Comercial – Horizonte temporal de proyectos**:
  - **Activos persistentes durante toda su vida**: Los proyectos en estados activos (Prospecto, Presupuestado, Negociación, Objeción) se muestran en el Dashboard Comercial durante toda su vigencia, independientemente del mes del filtro, hasta que se ganan o se pierden.
  - **Ganados/Perdidos visibles solo en el mes de cierre**: Cuando un proyecto pasa a estado Ganado o Perdido, se incluye en el Dashboard únicamente en el período en el que se cerró (según fecha de actualización), ya sea mes actual, mes específico o rango seleccionado. Al cambiar de mes queda fuera del Dashboard, evitando ruido de tratos cerrados en períodos anteriores.
  - **Total Acumulado como vista histórica**: Al seleccionar “Total Acumulado”, el Dashboard muestra nuevamente todos los proyectos (activos, ganados y perdidos) sin recorte temporal, funcionando como visión histórica completa del pipeline comercial.
- **Notificaciones Unificadas (Campana)**:
  - **Icono desactivado cuando no hay alertas**: En todos los paneles con campana de notificaciones (Dashboard Técnico, Dashboard Comercial, Panel de Administración Comercial, Panel de Administrador y Panel de Visor), cuando no existen alertas reales se muestra una campana desactivada (`🔕`) con estilo gris tenue.
  - **Mensaje coherente en popovers**: Al abrir el popover de notificaciones sin alertas se muestra siempre el mensaje “No hay alertas pendientes.” (o el equivalente del contexto), evitando paneles vacíos.
  - **Detección precisa de alertas comerciales**: En el Panel de Administración Comercial solo se considera que hay alertas cuando existen tratos con vencimientos relevantes (vencidos, hoy o próximos) o solicitudes de clientes pendientes; si todos los contadores están en cero, la campana se muestra desactivada.

## 1.2.60
- **Dashboard Comercial (adm_comercial y Comercial)**:
  - **Tarjetas de vencimientos con horizonte completo**: Las tarjetas de proyectos ordenados por fecha de cierre utilizan ahora siempre todos los tratos disponibles, independientemente del filtro de fecha seleccionado en las métricas. Esto permite ver vencimientos futuros (no solo los del mes actual) manteniendo las métricas resumidas filtradas por período.
  - **Botón de eliminación más claro**: En el formulario de edición de tratos, el botón para eliminar documentos adjuntos se rediseñó como “🗑 Eliminar documento”, ocupando todo el ancho de su columna para mejorar legibilidad y evitar saltos de línea extraños.
  - **Edición de documentos sin enlace de descarga redundante**: Se eliminó el enlace “Descargar …” dentro del formulario de edición de tratos. La descarga de archivos se concentra en la sección de detalle “📂 Documentos”, reduciendo ruido visual en el modal de edición.
- **Gestión de Documentos de Proyectos**:
  - **Subida de documentos por administradores**: Al adjuntar documentos desde el formulario de edición de tratos, los archivos nuevos se registran utilizando siempre el dueño real del proyecto (`owner_user_id`) para la verificación de permisos. Esto permite que `adm_comercial` agregue documentos a proyectos de los vendedores sin que se descarten silenciosamente.
- **Visualización de Métricas por Cliente**:
  - **Nombres de clientes más limpios en gráficos**: La lógica de abreviación de nombres de cliente en los gráficos de “Horas por Cliente” se refinó para eliminar sufijos societarios comunes (S.A., SRL, SAS, SAIC, etc.) y tomar la primera palabra significativa. Ejemplos: “IKE ASISTENCIA ARGENTINA S.A.” → “IKE”, “SYSTEMSCORP S.A.” → “SYSTEMSCORP”. El nombre completo sigue disponible en el tooltip.
- **Backups y Restauración**:
  - **Restauración tolerante a columnas antiguas**: Durante la restauración completa desde Excel, antes de insertar los datos de cada hoja, el sistema intersecta las columnas del archivo con las columnas reales de la tabla en PostgreSQL. Cualquier columna desconocida (por ejemplo, la antigua columna `jurisdiccion` en `feriados`) se ignora automáticamente, evitando errores críticos durante la restauración en bases con esquema actualizado.
  - **Respeto de restricciones NOT NULL**: Se mantiene la lógica de rellenar valores por defecto para columnas `NOT NULL` según su tipo (texto vacío, 0, False), aplicándola únicamente sobre las columnas que realmente existen en la tabla.
- **Flujo Comercial – Solicitud de Nuevo Cliente**:
  - **Estabilidad del modal “Cargar cliente”**: Se corrigió un error `UnboundLocalError` relacionado con el uso de `safe_rerun` en el formulario manual de solicitud de nuevo cliente, asegurando que el modal funcione de forma consistente tanto para el usuario comercial como para `adm_comercial`.

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
  - **Columnas ocultas por defecto**: La vista “📋 Lista” oculta las columnas `activo` e `id_cliente`.
  - **Limpieza automática de columnas vacías**: Columnas completamente vacías (valores vacíos/None) se ocultan por defecto para mejorar la legibilidad.
  - **Orden de columnas por defecto**: La tabla se muestra en el siguiente orden de prioridad: `CUIT`, `Nombre`, `Email`, `Teléfono`, `Celular`, `Web (URL)` y luego el resto de columnas disponibles.
 - **Dashboard Comercial – Pestaña “🏢 Clientes”**:
   - **Nueva pestaña**: El usuario Comercial dispone de una pestaña “🏢 Clientes” que muestra la misma tabla de clientes de la vista “📋 Lista”, con las mismas reglas de visualización (oculta `activo` e `id_cliente`, oculta columnas vacías y orden preferente de columnas).
   - **Subpestañas**: La pestaña “🏢 Clientes” ahora incluye “Clientes” y “Marcas”. La subpestaña “Marcas” muestra la tabla de marcas con las mismas reglas de visualización (oculta `id_marca` y `activa`, oculta columnas vacías y orden por `CUIT`, `Nombre`, `Email`, `Teléfono`, `Celular`, `Web (URL)`).
 - **Dashboard Comercial – Navegación en tarjetas**:
   - **Tarjeta clickeable**: En el Dashboard Comercial (adm_comercial), la tarjeta completa del proyecto es clickeable y lleva al detalle del proyecto en la pestaña “📂 Tratos Dpto Comercial”.
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
  - **Expander por defecto**: “👤 Generar Usuarios desde Nómina” ahora está colapsado por defecto para reducir ruido visual al ingresar a la pantalla.
- **Gestión de Clientes**:
  - **Expander por defecto**: “Agregar Nuevo Cliente” ahora está colapsado por defecto. La carga masiva permanece replegada y al final de la vista, manteniendo la tabla como protagonista.
- **Gestión de Grupos**:
  - **Expander por defecto**: “Agregar Nuevo Grupo” ahora está colapsado por defecto, manteniendo el foco en la lista de grupos y sus acciones.

## 1.2.56
- **Formulario de Solicitud de Nuevo Cliente**:
  - **Indicadores de Campos Obligatorios**: Se añadieron asteriscos (*) a los campos obligatorios del modal de “Cargar cliente” (CUIT, Nombre, Email, Teléfono y Celular) tanto para el flujo Comercial como para adm_comercial, en línea con el formulario de “Crear Nuevo Contacto”.
- **Dashboard Comercial**:
  - **Nombre abreviado en encabezado**: El título ahora muestra solo el primer nombre y el primer apellido del usuario. Ejemplo: “Ana Pérez”.

## 1.2.55
- **Consistencia de UI (Temas Claro/Oscuro)**:
  - **Tarjetas de Solicitudes**: Se estandarizó el diseño de las tarjetas de "Solicitudes de Clientes" (Admin y Visor Comercial) para que coincidan visualmente con las tarjetas de Contactos. Se implementó el uso de variables nativas de Streamlit (`secondary-background-color`, `text-color`) para garantizar una adaptación perfecta y automática a los temas Claro y Oscuro, eliminando estilos hardcodeados que causaban problemas de legibilidad.
- **Normalización de Datos (Nombres)**:
  - **Soporte para Nombres Compuestos**: Se actualizó la lógica de capitalización de nombres y apellidos (en edición de perfil, carga de nómina y visualización) para utilizar el formato de "Título" (Title Case) en lugar de solo capitalizar la primera letra. Esto corrige la visualización de nombres compuestos (ej. "Juan Carlos" en lugar de "Juan carlos").
- **Correcciones Visuales (Mis Tratos)**:
  - **Renderizado de Tarjetas**: Se solucionó un error que mostraba código HTML crudo en las tarjetas de proyecto cuando la fecha de cierre era lejana.
  - **Visualización de Fechas**: Se unificó el criterio de visualización de vencimientos; ahora las fechas lejanas (>30 días) muestran explícitamente los días restantes en color verde, manteniendo la consistencia visual con los vencimientos próximos.

## 1.2.54
- **Mejoras Visuales (Login)**:
  - **Legibilidad de Mensajes**: Se aumentó el tamaño de fuente de los mensajes de alerta (éxito, error, advertencia) en la pantalla de inicio de sesión para mejorar la legibilidad y la experiencia del usuario.

## 1.2.53
- **Mejoras de UI y Estabilidad**:
  - **Optimización de Header (Minimalista)**: Se implementó un encabezado transparente que maximiza el espacio vertical sin sacrificar funcionalidad. Se eliminaron márgenes innecesarios y se aseguró la accesibilidad del menú de configuración mediante una barra de herramientas flotante con visibilidad forzada (`z-index` elevado).
  - **Corrección de Logout**: Se solucionó un problema de recarga infinita al cerrar sesión, eliminando llamadas redundantes (`st.rerun`) y gestionando correctamente la limpieza de cookies y estado.

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

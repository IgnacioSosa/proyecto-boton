# Sistema de Registro de Horas (SIGO)

## 📦 Instalación

### Prerrequisitos
- Python 3.9+
- PostgreSQL 16+ instalado y en ejecución
- Acceso a un usuario administrador de PostgreSQL (usualmente `postgres`) para la configuración inicial

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

4. **Configurar Base de Datos**
   El proyecto incluye un script interactivo que configura todo automáticamente (Base de datos, Usuario, .env y Tablas).

   Ejecuta el siguiente comando y sigue las instrucciones en pantalla:
   ```bash
   python regenerate_database.py
   ```
   
   **¿Qué hace este script?**
   1. Te pedirá credenciales de administrador PostgreSQL (ej. usuario `postgres`) para poder crear la base de datos.
   2. Creará la base de datos `sigo_db` si no existe.
   3. Creará el usuario de aplicación `sigo`.
   4. Te pedirá definir una contraseña segura para el usuario `sigo`.
   5. Generará automáticamente el archivo `.env` con la configuración correcta.
   6. Creará todas las tablas y datos iniciales del sistema.

5. **Ejecutar la aplicación**
   ```bash
   streamlit run app.py
   ```

6. **Asistente de Configuración Inicial**
   Al ingresar por primera vez como administrador, verás un asistente de 4 pasos:
   1. **Subir planilla de nómina:** Carga inicial de empleados.
   2. **Generar usuarios:** Crea usuarios de sistema basados en la nómina.
   3. **Definir rutas de almacenamiento:** (NUEVO) Configura dónde se guardarán los archivos adjuntos y documentos del proyecto. Puedes usar rutas locales o discos externos.
   4. **Subir registros:** Importación histórica de horas (opcional).

7. **Ingreso al sistema**
   - **Usuario:** `admin`
   - **Contraseña:** `admin`
   - *(Se recomienda cambiar esta contraseña inmediatamente después del primer ingreso)*


  ```

- **Regeneración de Base de Datos:**
  El script `regenerate_database.py` ahora es inteligente y detecta si el usuario ya existe, permitiéndote validar su contraseña o resetearla a valores por defecto (`sigo`) si la olvidaste.
  ```bash
  python regenerate_database.py
  ```

### Comandos Útiles

El script `regenerate_database.py` tiene opciones adicionales para mantenimiento:

```bash
# Ayuda
python regenerate_database.py --help

# Regeneración automática (para entornos CI/CD o resets rápidos, usa credenciales existentes en .env)
python regenerate_database.py --auto

# Verificar conexión a la base de datos
python regenerate_database.py --check-connection

# Desbloquear un usuario (por exceso de intentos fallidos)
python regenerate_database.py --unlock [nombre_usuario]

# Corregir hash de contraseña de admin (si no puedes entrar)
python regenerate_database.py --fix-hash
```

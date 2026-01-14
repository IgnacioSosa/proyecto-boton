# Sistema de Registro de Horas

## 📦 Instalación

### Prerrequisitos
- Python 3.8+
- PostgreSQL 16+ (recomendado)
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
- Usuario por defecto: `admin`
- Contraseña por defecto: `admin`

6. **Ejecutar la aplicación**
```bash
streamlit run app.py
```

### Herramientas de Base de Datos (opcional)
El script `regenerate_database.py` incluye varias utilidades de mantenimiento:

```bash
# Ver ayuda completa
python regenerate_database.py --help

# Regeneración automática (borra y crea todo)
python regenerate_database.py --auto

# Utilidades sin borrado
python regenerate_database.py --check-connection  # Verificar conexión
python regenerate_database.py --fix-hash          # Arreglar login admin
python regenerate_database.py --setup-data        # Re-insertar datos base
```


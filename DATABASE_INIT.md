# Database Initialization Documentation

## Overview
Se ha implementado un sistema automático de inicialización de bases de datos que se ejecuta al iniciar la aplicación.

## Cambios Realizados

### 1. Nuevo Servicio: `app/services/database_init_service.py`
- **Propósito**: Gestionar la inicialización de las tablas de base de datos
- **Funciones principales**:
  - `init_database()`: Verifica que todas las tablas necesarias existan y las crea si no están presentes
  - `verify_database_connection()`: Verifica que la conexión a la base de datos sea válida

### 2. Modificación: `app/main.py`
Se agregó la inicialización de la base de datos en el evento `lifespan` de FastAPI:
- Se verifica la conexión a la base de datos
- Se crean automáticamente todas las tablas que no existan
- Se registran los eventos en los logs para auditoría

## Tablas Creadas Automáticamente
La aplicación crea automáticamente las siguientes tablas:
1. `publications` - Publicaciones/documentos
2. `subjects` - Categorías/asuntos
3. `publication_subjects` - Relación muchos-a-muchos entre publicaciones y asuntos
4. `contributors` - Autores/asesores de las publicaciones
5. `social_media_records` - Registros de redes sociales
6. `excluded_publication` - Publicaciones excluidas

## Flujo de Inicialización

```
1. FastAPI inicia
   ↓
2. Se ejecuta el lifespan startup
   ↓
3. Se verifica la conexión a la BD
   ↓
4. Se comparan las tablas existentes con las esperadas
   ↓
5. Si hay tablas faltantes, se crean automáticamente
   ↓
6. Se registran todos los eventos en los logs
   ↓
7. Se inicia el scheduler de trabajos programados
```

## Logs
La inicialización genera los siguientes logs:
- `Starting application initialization...` - Inicio del proceso
- `Database connection verified successfully` - Conexión exitosa (si aplica)
- `Creating missing tables: {...}` - Si hay tablas por crear
- `Successfully created X table(s)` - Confirmación de creación
- `All required tables already exist` - Si todas las tablas ya existen
- `Database initialization completed successfully` - Fin del proceso

## Manejo de Errores
Si ocurre un error durante la inicialización:
- Se registra un mensaje de error detallado en los logs
- Se lanza una excepción que detiene la aplicación
- Esto asegura que la aplicación no inicie sin una base de datos correctamente configurada

## Requisitos
- SQLAlchemy 2.0+
- AsyncIO support
- Modelos SQLAlchemy correctamente definidos en `app/models/`

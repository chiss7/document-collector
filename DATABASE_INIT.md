# Database Initialization Documentation

## Overview
El proyecto usa **Alembic** para gestionar las migraciones de base de datos.
Las migraciones se ejecutan automáticamente al iniciar la aplicación.

## Migraciones Automáticas en Startup
La función `init_database()` en `app/services/database_init_service.py` ejecuta
`alembic upgrade head` al arrancar la aplicación, aplicando cualquier migración
pendiente. Las tablas se crean solo si no existen (`CREATE TABLE IF NOT EXISTS`).

## Estructura de Migraciones
- `alembic/versions/` — contiene los archivos de migración
- `alembic/env.py` — configuración de Alembic (importa modelos, URL de conexión)
- `alembic.ini` — configuración general de Alembic

## Comandos Útiles

### Crear una nueva migración automática (después de cambiar modelos)
```bash
alembic revision --autogenerate -m "descripcion_del_cambio"
```

### Revisar el SQL que generará una migración sin ejecutarla
```bash
alembic upgrade head --sql
```

### Ejecutar migraciones manualmente
```bash
alembic upgrade head
```

### Revertir la última migración
```bash
alembic downgrade -1
```

### Ver el historial de migraciones
```bash
alembic history
```

### Ver el estado actual
```bash
alembic current
```

## Tablas Gestionadas
1. `publications` — Publicaciones/documentos
2. `subjects` — Categorías/asuntos
3. `publication_subjects` — Relación muchos-a-muchos entre publicaciones y asuntos
4. `contributors` — Autores/asesores de las publicaciones
5. `social_media_records` — Registros de redes sociales
6. `excluded_publication` — Publicaciones excluidas

## Notas Técnicas
- La conexión de Alembic usa el driver **psycopg** (síncrono), mientras que la app
  usa **asyncpg** (asíncrono). La conversión se hace automáticamente en `env.py`
  reemplazando `+asyncpg` por `+psycopg` en la URL.
- La migración inicial usa `CREATE TABLE IF NOT EXISTS` para ser segura tanto en
  bases de datos nuevas como existentes.

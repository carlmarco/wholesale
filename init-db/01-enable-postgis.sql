-- Enable PostGIS extension for spatial data support
-- This script runs automatically when the PostgreSQL container starts
-- MUST run before any Alembic migrations to ensure Geography columns work

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Verify PostGIS is installed
SELECT postgis_version();

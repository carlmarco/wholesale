-- Enable PostGIS extension for spatial data
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Create wholesaler database if not exists
SELECT 'CREATE DATABASE wholesaler'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'wholesaler')\gexec

-- Create airflow database for Airflow metadata
SELECT 'CREATE DATABASE airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE wholesaler TO wholesaler_user;
GRANT ALL PRIVILEGES ON DATABASE airflow TO wholesaler_user;

# Database Schema - Phase 2

## Overview

Production-grade PostgreSQL database with PostGIS extension for spatial data. Uses parcel_id_normalized as the primary key across all property-related tables.

---

## Entity Relationship Diagram

```
┌─────────────────────┐
│     properties      │ ◄─┐
├─────────────────────┤   │
│ parcel_id_normalized│PK │
│ parcel_id_original  │   │
│ situs_address       │   │
│ coordinates (GEOG)  │   │
│ created_at          │   │
│ updated_at          │   │
│ is_active           │   │
└─────────────────────┘   │
         △                │
         │                │
         │ 1:1            │
┌────────┼────────┬───────┼───────┬────────────┐
│        │        │       │       │            │
│  ┌─────┴─────┐ │ ┌─────┴─────┐ │  ┌─────────┴────────┐
│  │ tax_sales │ │ │foreclosures│ │  │ property_records │
│  ├───────────┤ │ ├───────────┤ │  ├──────────────────┤
│  │ id        │PK│ │ id        │PK│  │ id               │PK
│  │ parcel_id │FK│ │ parcel_id │FK│  │ parcel_id        │FK
│  │ tda_number│ │ │ borrower  │ │  │ total_mkt        │
│  │ sale_date │ │ │ default_amt│ │  │ total_assd       │
│  │ deed_status│ │ │ auction_dt│ │  │ taxes            │
│  │ created_at│ │ │ lender    │ │  │ year_built       │
│  │ updated_at│ │ │ created_at│ │  │ living_area      │
│  └───────────┘ │ │ updated_at│ │  │ lot_size         │
│                │ └───────────┘ │  │ created_at       │
│                │               │  │ updated_at       │
│                │               │  └──────────────────┘
│                │               │
│  ┌─────────────┴──────┐       │
│  │  code_violations   │       │
│  ├────────────────────┤       │
│  │ id                 │PK     │
│  │ parcel_id          │FK     │
│  │ case_number        │       │
│  │ violation_type     │       │
│  │ status             │       │
│  │ opened_date        │       │
│  │ closed_date        │       │
│  │ coordinates (GEOG) │       │
│  │ created_at         │       │
│  │ updated_at         │       │
│  └────────────────────┘       │
│                               │
│  ┌──────────────────────────┐ │
│  │      lead_scores         │ │
│  ├──────────────────────────┤ │
│  │ id                       │PK│
│  │ parcel_id                │FK│
│  │ total_score              │  │
│  │ distress_score           │  │
│  │ value_score              │  │
│  │ location_score           │  │
│  │ urgency_score            │  │
│  │ tier (A/B/C/D)           │  │
│  │ reasons (JSONB)          │  │
│  │ scored_at                │  │
│  │ created_at               │  │
│  └──────────────────────────┘  │
│           │                     │
│           │ 1:N                 │
│           ▼                     │
│  ┌──────────────────────────┐  │
│  │  lead_score_history      │  │
│  ├──────────────────────────┤  │
│  │ id                       │PK│
│  │ lead_score_id            │FK│
│  │ total_score              │  │
│  │ tier                     │  │
│  │ snapshot_date            │  │
│  │ created_at               │  │
│  └──────────────────────────┘  │
│                                 │
└─────────────────────────────────┘

┌────────────────────────────┐
│   data_ingestion_runs      │
├────────────────────────────┤
│ id                         │PK
│ source_type                │ (enum: tax_sales, foreclosures, etc.)
│ status                     │ (enum: success, failure, partial)
│ records_processed          │
│ records_inserted           │
│ records_updated            │
│ records_failed             │
│ error_message              │
│ started_at                 │
│ completed_at               │
│ created_at                 │
└────────────────────────────┘
```

---

## Table Definitions

### 1. `properties` (Master Property Table)

Primary table for all properties. One record per unique parcel.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| parcel_id_normalized | VARCHAR(50) | PRIMARY KEY | Normalized parcel ID (digits only) |
| parcel_id_original | VARCHAR(50) | NOT NULL | Original parcel ID format |
| situs_address | VARCHAR(255) | | Standardized property address |
| city | VARCHAR(100) | | City name |
| state | VARCHAR(2) | | State abbreviation (FL) |
| zip_code | VARCHAR(10) | | 5-digit ZIP code |
| coordinates | GEOGRAPHY(POINT, 4326) | | WGS84 coordinates (PostGIS) |
| latitude | NUMERIC(10, 7) | CHECK (-90 <= latitude <= 90) | Latitude |
| longitude | NUMERIC(10, 7) | CHECK (-180 <= longitude <= 180) | Longitude |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | Record creation timestamp |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | Last update timestamp |
| is_active | BOOLEAN | NOT NULL DEFAULT TRUE | Soft delete flag |

**Indexes:**
- PRIMARY KEY on `parcel_id_normalized`
- GIST spatial index on `coordinates`
- B-tree index on `created_at`, `updated_at`
- B-tree index on `situs_address`

---

### 2. `tax_sales`

Tax sale property records (1:1 with properties).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| parcel_id_normalized | VARCHAR(50) | FOREIGN KEY UNIQUE | References properties |
| tda_number | VARCHAR(50) | | Tax deed application number |
| sale_date | DATE | | Scheduled tax sale date |
| deed_status | VARCHAR(100) | | Deed status |
| latitude | NUMERIC(10, 7) | | Original API latitude |
| longitude | NUMERIC(10, 7) | | Original API longitude |
| raw_data | JSONB | | Raw API response |
| data_source_timestamp | TIMESTAMP | | When scraped from API |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**Indexes:**
- UNIQUE on `parcel_id_normalized`
- B-tree on `sale_date`
- B-tree on `tda_number`

---

### 3. `foreclosures`

Foreclosure property records (1:1 with properties).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| parcel_id_normalized | VARCHAR(50) | FOREIGN KEY UNIQUE | References properties |
| borrowers_name | VARCHAR(255) | | Borrower name |
| situs_address | VARCHAR(255) | | Property address from API |
| default_amount | NUMERIC(12, 2) | | Amount in default |
| opening_bid | NUMERIC(12, 2) | | Opening bid amount |
| auction_date | DATE | | Foreclosure auction date |
| lender_name | VARCHAR(255) | | Lender/bank name |
| property_type | VARCHAR(100) | | Property type |
| latitude | NUMERIC(10, 7) | | Original API latitude |
| longitude | NUMERIC(10, 7) | | Original API longitude |
| raw_data | JSONB | | Raw API response |
| data_source_timestamp | TIMESTAMP | | When scraped from API |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**Indexes:**
- UNIQUE on `parcel_id_normalized`
- B-tree on `auction_date`
- B-tree on `default_amount`
- GIN on `raw_data` (for JSONB queries)

---

### 4. `property_records`

Property appraiser valuation records (1:1 with properties).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| parcel_id_normalized | VARCHAR(50) | FOREIGN KEY UNIQUE | References properties |
| owner_name | VARCHAR(255) | | Property owner name |
| total_mkt | NUMERIC(12, 2) | | Total market value |
| total_assd | NUMERIC(12, 2) | | Total assessed value |
| taxable | NUMERIC(12, 2) | | Taxable value |
| taxes | NUMERIC(12, 2) | | Annual taxes |
| year_built | INTEGER | CHECK (year_built >= 1800) | Year built |
| living_area | INTEGER | | Living area (sq ft) |
| lot_size | INTEGER | | Lot size (sq ft) |
| equity_percent | NUMERIC(6, 2) | | Calculated equity % |
| tax_rate | NUMERIC(6, 4) | | Calculated tax rate % |
| latitude | NUMERIC(10, 7) | | Original API latitude |
| longitude | NUMERIC(10, 7) | | Original API longitude |
| raw_data | JSONB | | Raw API response |
| data_source_timestamp | TIMESTAMP | | When scraped from API |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**Indexes:**
- UNIQUE on `parcel_id_normalized`
- B-tree on `total_mkt`
- B-tree on `equity_percent`
- B-tree on `year_built`

---

### 5. `code_violations`

Code enforcement violations (many:1 with properties).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| parcel_id_normalized | VARCHAR(50) | FOREIGN KEY | References properties |
| case_number | VARCHAR(100) | UNIQUE | Violation case number |
| violation_type | VARCHAR(255) | | Type of violation |
| status | VARCHAR(50) | | OPEN or CLOSED |
| opened_date | DATE | | Date violation opened |
| closed_date | DATE | | Date violation closed |
| coordinates | GEOGRAPHY(POINT, 4326) | | WGS84 coordinates |
| latitude | NUMERIC(10, 7) | | Latitude |
| longitude | NUMERIC(10, 7) | | Longitude |
| raw_data | JSONB | | Raw API/CSV data |
| data_source_timestamp | TIMESTAMP | | When loaded |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**Indexes:**
- UNIQUE on `case_number`
- B-tree on `parcel_id_normalized`
- GIST spatial index on `coordinates`
- B-tree on `status`
- B-tree on `opened_date`

---

### 6. `lead_scores`

Current lead scores for properties (1:1 with properties).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| parcel_id_normalized | VARCHAR(50) | FOREIGN KEY UNIQUE | References properties |
| total_score | NUMERIC(5, 2) | CHECK (0 <= total_score <= 100) | Total lead score |
| distress_score | NUMERIC(5, 2) | | Distress component (35%) |
| value_score | NUMERIC(5, 2) | | Value component (30%) |
| location_score | NUMERIC(5, 2) | | Location component (20%) |
| urgency_score | NUMERIC(5, 2) | | Urgency component (15%) |
| tier | VARCHAR(1) | CHECK (tier IN ('A', 'B', 'C', 'D')) | Lead tier |
| reasons | JSONB | | Scoring reasons |
| scored_at | TIMESTAMP | NOT NULL | When score was calculated |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**Indexes:**
- UNIQUE on `parcel_id_normalized`
- B-tree on `total_score DESC`
- B-tree on `tier`
- B-tree on `scored_at`
- GIN on `reasons` (for JSONB queries)

---

### 7. `lead_score_history`

Historical snapshots of lead scores for trending analysis (many:1 with lead_scores).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| lead_score_id | INTEGER | FOREIGN KEY | References lead_scores |
| parcel_id_normalized | VARCHAR(50) | NOT NULL | Denormalized for queries |
| total_score | NUMERIC(5, 2) | | Historical total score |
| tier | VARCHAR(1) | | Historical tier |
| snapshot_date | DATE | NOT NULL | Date of snapshot |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**Indexes:**
- B-tree on `lead_score_id`
- B-tree on `parcel_id_normalized`
- B-tree on `snapshot_date DESC`
- UNIQUE on `(lead_score_id, snapshot_date)`

---

### 8. `data_ingestion_runs`

ETL job execution metadata and tracking.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| source_type | VARCHAR(50) | NOT NULL | tax_sales, foreclosures, etc. |
| status | VARCHAR(20) | CHECK (status IN ('success', 'failure', 'partial')) | Job status |
| records_processed | INTEGER | DEFAULT 0 | Total records processed |
| records_inserted | INTEGER | DEFAULT 0 | Records inserted |
| records_updated | INTEGER | DEFAULT 0 | Records updated |
| records_failed | INTEGER | DEFAULT 0 | Records failed |
| error_message | TEXT | | Error details if failed |
| error_details | JSONB | | Structured error data |
| started_at | TIMESTAMP | NOT NULL | Job start time |
| completed_at | TIMESTAMP | | Job completion time |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**Indexes:**
- B-tree on `source_type`
- B-tree on `status`
- B-tree on `started_at DESC`

---

## Spatial Queries with PostGIS

### Find Properties Within Radius of Violations

```sql
SELECT
    p.parcel_id_normalized,
    p.situs_address,
    COUNT(v.id) as nearby_violations
FROM properties p
LEFT JOIN code_violations v ON
    ST_DWithin(
        p.coordinates::geography,
        v.coordinates::geography,
        402.336  -- 0.25 miles in meters
    )
WHERE p.is_active = true
GROUP BY p.parcel_id_normalized, p.situs_address;
```

### Find Nearest Violation to Property

```sql
SELECT
    v.case_number,
    v.violation_type,
    ST_Distance(
        p.coordinates::geography,
        v.coordinates::geography
    ) / 1609.34 as distance_miles  -- Convert meters to miles
FROM properties p
CROSS JOIN LATERAL (
    SELECT * FROM code_violations v
    WHERE ST_DWithin(
        p.coordinates::geography,
        v.coordinates::geography,
        402.336
    )
    ORDER BY p.coordinates <-> v.coordinates
    LIMIT 1
) v
WHERE p.parcel_id_normalized = '123456789012345';
```

---

## Data Retention & Archival

- `is_active` flag for soft deletes (never hard delete properties)
- `lead_score_history` snapshots retained for 2 years
- `data_ingestion_runs` logs retained for 1 year
- Partition `lead_score_history` by year for performance

---

## Performance Considerations

1. **Indexes:** All foreign keys indexed, spatial GIST indexes on geography columns
2. **Partitioning:** Consider range partitioning on `lead_score_history` by `snapshot_date`
3. **Materialized Views:** Create for dashboard queries (Tier A count, avg scores, etc.)
4. **Connection Pooling:** SQLAlchemy pool_size=20, max_overflow=10
5. **Batch Operations:** Use bulk inserts for >1000 records
6. **Query Optimization:** Use EXPLAIN ANALYZE for slow queries

---

## Migration Strategy

1. Initial schema creation via Alembic
2. Migrate existing in-memory data to database
3. Implement incremental updates (not full scrape)
4. Add partitioning and materialized views after data volume grows

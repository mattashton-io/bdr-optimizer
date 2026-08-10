-- billing-queries.sql
-- High-performance Standard SQL templates for querying GCP Backup & DR and storage billing data.
-- Replace `your-gcp-project.billing_dataset.gcp_billing_export_v1_xxxxxx` with your actual billing export table path.

--------------------------------------------------------------------------------
-- QUERY 1: Historical Cost Breakdown by Project, Region, and BDR SKU
--------------------------------------------------------------------------------
-- Retrieves the historical costs of Backup and DR service, including vault storage
-- and snapshots, grouped by Project, Region, and SKU.

SELECT
  project.id AS project_id,
  project.name AS project_name,
  location.region AS region,
  sku.description AS sku_description,
  SUM(cost) AS total_raw_cost,
  SUM(credits.amount) AS total_credits,
  SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost,
  currency
FROM
  `your-gcp-project.billing_dataset.gcp_billing_export_v1_xxxxxx`
WHERE
  -- Filter for GCP Backup & DR services, Vaults, and related Storage/Snapshot SKUs
  (service.description LIKE '%Backup and DR%'
   OR sku.description LIKE '%Backup Vault%'
   OR (service.description = 'Cloud Storage' AND sku.description LIKE '%Snapshot%'))
  -- Exclude negative costs/corrections if desired, or keep to show active net
  AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY
  project_id,
  project_name,
  region,
  sku_description,
  currency
ORDER BY
  net_cost DESC;


--------------------------------------------------------------------------------
-- QUERY 2: Backup Storage Cost Breakdown by Storage Tier / Class
--------------------------------------------------------------------------------
-- Groups storage costs of Backup & DR by active storage tiers (Standard, Nearline,
-- Coldline, Archive) to analyze tiering optimization opportunities.

SELECT
  project.id AS project_id,
  CASE
    WHEN LOWER(sku.description) LIKE '%archive%' THEN 'Archive Storage'
    WHEN LOWER(sku.description) LIKE '%coldline%' THEN 'Coldline Storage'
    WHEN LOWER(sku.description) LIKE '%nearline%' THEN 'Nearline Storage'
    ELSE 'Standard Storage'
  END AS storage_tier,
  SUM(usage.amount) AS total_usage_amount,
  usage.unit AS usage_unit,
  SUM(cost) AS total_cost,
  currency
FROM
  `your-gcp-project.billing_dataset.gcp_billing_export_v1_xxxxxx`
WHERE
  service.description LIKE '%Backup and DR%'
  AND sku.description LIKE '%Storage%'
  AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY
  project_id,
  storage_tier,
  usage_unit,
  currency
ORDER BY
  total_cost DESC;


--------------------------------------------------------------------------------
-- QUERY 3: 30-Day Cost Projection based on Recent Daily Burn Rate
--------------------------------------------------------------------------------
-- Analyzes daily cost patterns over the past 7 days to calculate an average daily
-- burn rate, then projects the estimated next 30 days of storage and egress costs.

WITH daily_burn_rates AS (
  SELECT
    DATE(usage_start_time) AS billing_date,
    SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS daily_net_cost
  FROM
    `your-gcp-project.billing_dataset.gcp_billing_export_v1_xxxxxx`
  WHERE
    (service.description LIKE '%Backup and DR%'
     OR sku.description LIKE '%Backup Vault%'
     OR (service.description = 'Cloud Storage' AND sku.description LIKE '%Snapshot%'))
    -- Filter past 7 days to establish current burn rate baseline
    AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  GROUP BY
    billing_date
),

avg_daily_rate AS (
  SELECT
    AVG(daily_net_cost) AS avg_daily_burn
  FROM
    daily_burn_rates
)

SELECT
  avg_daily_burn,
  (avg_daily_burn * 30) AS projected_30_day_cost,
  (avg_daily_burn * 365) AS projected_annual_cost,
  'USD' AS currency
FROM
  avg_daily_rate;

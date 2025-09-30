CREATE OR REFRESH MATERIALIZED VIEW mma_fe_innovation.mma.device_adverse_events
AS
SELECT
  -- Generate a random date in the past 2 years from today
  date_add(
    current_date(),
    -CAST(rand() * 730 AS INT)
  ) AS event_date,
  device_name,
  -- Generate an adverse event/recall description using a built-in AI function
  ai_gen(
    'Generate a realistic adverse event or recall description for a medical device. Do not add any unnecessary text or prefixes. The device name is:' || device_name
  ) AS adverse_event_description,
  -- Assign a random severity level: "low", "medium", or "high"
  ai_query(
    'databricks-gpt-oss-120b',
    CONCAT('Generate a severity level, only 1 of these 3 values: high, medium, low. Use this adverse event description to generate the level:', `adverse_event_description`)
  ) AS severity_level
FROM (
  SELECT DISTINCT device_name
  FROM mma_fe_innovation.mma.medical_orders_silver
  ORDER BY rand()
  LIMIT 1500
) sampled_devices;
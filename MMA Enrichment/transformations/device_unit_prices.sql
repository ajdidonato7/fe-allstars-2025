CREATE OR REFRESH MATERIALIZED VIEW device_unit_prices
AS
SELECT
  device_name,
  CAST(
    1 + FLOOR(POWER(RAND(), 3) * 999)
    AS INT
  ) AS unit_price
FROM (
  SELECT DISTINCT device_name
  FROM mma_fe_innovation.mma.medical_orders_silver
);
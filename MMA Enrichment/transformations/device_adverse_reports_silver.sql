CREATE OR REFRESH MATERIALIZED VIEW mma_fe_innovation.mma.device_adverse_reports_silver AS
SELECT
  event_date,
  device_name,
  CASE
    WHEN adverse_event_description LIKE "Here's a realistic adverse event or recall description for the%"
      THEN ltrim(
        substr(
          adverse_event_description,
          length("Here's a realistic adverse event or recall description for the medical device:") + 1
        )
      )
    WHEN adverse_event_description LIKE "Here's a realistic adverse event/recall description%"
      THEN ltrim(
        substr(
          adverse_event_description,
          length("Here's a realistic adverse event/recall description") + 1
        )
      )
    ELSE adverse_event_description
  END AS adverse_event_description,
  severity_level
FROM mma_fe_innovation.mma.device_adverse_events;
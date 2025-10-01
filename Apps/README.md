# 🏥 Medical Device Retailer Order & Adverse Events Tracker

A Dash web application for tracking medical device retailer orders and associated adverse events.

## Quick Start

### Option 1: Interactive Setup (Recommended)
Run the interactive setup script to configure your environment:

```bash
python3 setup_env.py
```

### Option 2: Manual Setup
1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your database connection details

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. **Debug your connection (recommended):**
   ```bash
   python3 debug_connection.py
   ```

5. Run the application:
   ```bash
   python3 app.py
   ```

6. Open your browser to: http://localhost:8050

## Debugging Connection Issues

If you're having trouble connecting to your database, use the debugging tool:

```bash
python3 debug_connection.py
```

This will check:
- ✅ Environment variables
- ✅ Databricks authentication
- ✅ Database connection
- ✅ Required tables
- ✅ Sample data queries

The app also displays real-time connection status at the top of the page.

## Required Environment Variables

The application needs these environment variables to connect to your PostgreSQL database:

| Variable | Description | Example |
|----------|-------------|---------|
| `PGDATABASE` | Database name | `main` |
| `PGUSER` | Your Databricks username | `john.doe@company.com` |
| `PGHOST` | Databricks SQL warehouse hostname | `dbc-abc123.cloud.databricks.com` |
| `PGPORT` | Database port | `443` |
| `PGSSLMODE` | SSL mode | `require` |
| `PGAPPNAME` | Application name | `medical_device_tracker` |

## Features

### 🔍 Retailer Order Lookup
- Search for orders by medical device retailer name
- View order details including:
  - Order ID
  - Order Date
  - Device Name
  - Quantity

### ⚠️ Adverse Events Integration
- Automatically displays adverse events for devices in orders
- Color-coded severity levels:
  - 🔴 High severity
  - 🟡 Medium severity
  - 🟢 Low severity
- Detailed event information including:
  - Event Date
  - Event Description
  - Severity Level

## Database Requirements

Your database must contain these tables:

### `synced_order_table_feallstars`
- `order_id` (bigint)
- `order_date` (date)
- `retailer_name` (string)
- `device_name` (string)
- `quantity` (int)

### `synced_table_adverse_events`
- `event_date` (date)
- `device_name` (string)
- `adverse_event_description` (string)
- `severity_level` (string)

## Authentication

The app uses Databricks OAuth token authentication. Make sure you're logged in:

```bash
databricks auth login
```

## Troubleshooting

See [SETUP.md](SETUP.md) for detailed setup instructions and troubleshooting guide.

## Files

- `app.py` - Main application
- `requirements.txt` - Python dependencies
- `setup_env.py` - Interactive environment setup script
- `.env.example` - Environment variables template
- `SETUP.md` - Detailed setup guide
- `README.md` - This file
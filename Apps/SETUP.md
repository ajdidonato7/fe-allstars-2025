# Medical Device Tracker Setup Guide

## Environment Variables Setup

The application requires several environment variables to connect to your PostgreSQL database (typically a Databricks SQL warehouse). Follow these steps to set them up:

### Step 1: Create Environment File

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file with your actual database connection details:
   ```bash
   nano .env
   # or use your preferred text editor
   ```

### Step 2: Required Environment Variables

Fill in these variables in your `.env` file:

| Variable | Description | Example |
|----------|-------------|---------|
| `PGDATABASE` | Your database name | `main` |
| `PGUSER` | Your Databricks username/email | `john.doe@company.com` |
| `PGHOST` | Your Databricks SQL warehouse hostname | `dbc-12345678-abcd.cloud.databricks.com` |
| `PGPORT` | Database port (usually 443 for Databricks) | `443` |
| `PGSSLMODE` | SSL mode (should be 'require') | `require` |
| `PGAPPNAME` | Application name (any descriptive name) | `medical_device_tracker` |

### Step 3: Finding Your Databricks Connection Details

To find your Databricks connection details:

1. **Log into your Databricks workspace**
2. **Go to SQL Warehouses** (in the sidebar)
3. **Click on your SQL warehouse**
4. **Go to "Connection details" tab**
5. **Copy the following information:**
   - **Server hostname** → use for `PGHOST`
   - **Port** → use for `PGPORT` (usually 443)
   - **HTTP path** → not needed for this app

### Step 4: Authentication

The app uses Databricks OAuth token authentication. Make sure you're logged into the Databricks CLI:

```bash
databricks auth login
```

### Step 5: Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### Step 6: Run the Application

```bash
python3 app.py
```

The app will be available at `http://localhost:8050`

## Database Tables Required

Make sure your database contains these tables:

### 1. `synced_order_table_feallstars`
- `order_id` (bigint)
- `order_date` (date)
- `retailer_name` (string)
- `device_name` (string)
- `quantity` (int)

### 2. `synced_table_adverse_events`
- `event_date` (date)
- `device_name` (string)
- `adverse_event_description` (string)
- `severity_level` (string)

## Troubleshooting

### Common Issues:

1. **"Failed to refresh OAuth token"**
   - Run `databricks auth login` to authenticate
   - Make sure you have access to the Databricks workspace

2. **"Connection refused"**
   - Check your `PGHOST` and `PGPORT` values
   - Ensure your SQL warehouse is running

3. **"Database does not exist"**
   - Verify your `PGDATABASE` value
   - Make sure you have access to the specified database

4. **"Table does not exist"**
   - Ensure the required tables exist in your database
   - Check table names and schema

### Environment Variable Loading Issues:

If environment variables aren't loading properly, you can set them manually in your shell:

```bash
export PGDATABASE=your_database_name
export PGUSER=your_username
export PGHOST=your_hostname
export PGPORT=443
export PGSSLMODE=require
export PGAPPNAME=medical_device_tracker
```

Then run the app:
```bash
python3 app.py
import dash
from dash import html, dcc, Input, Output, State, callback_context, dash_table
import psycopg
import os
import time
from databricks import sdk
from psycopg import sql
from psycopg_pool import ConnectionPool
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import json

# Load environment variables from .env file
load_dotenv()

# Database connection setup
workspace_client = None
postgres_password = None
last_password_refresh = 0
connection_pool = None
connection_status = {"status": "not_initialized", "message": ""}

def initialize_databricks_client():
    """Initialize Databricks client with error handling."""
    global workspace_client, connection_status
    try:
        # Temporarily remove DATABRICKS_TOKEN from environment to avoid conflicts
        # The token is used for the OpenAI client, not the SDK client
        databricks_token = os.environ.pop('DATABRICKS_TOKEN', None)
        
        try:
            workspace_client = sdk.WorkspaceClient()
            connection_status["status"] = "databricks_ok"
            connection_status["message"] = "Databricks client initialized"
            return True
        finally:
            # Restore the token for the OpenAI client
            if databricks_token:
                os.environ['DATABRICKS_TOKEN'] = databricks_token
                
    except Exception as e:
        connection_status["status"] = "databricks_error"
        connection_status["message"] = f"Databricks initialization failed: {str(e)}"
        print(f"❌ Databricks initialization error: {e}")
        return False

def refresh_oauth_token():
    """Refresh OAuth token if expired."""
    global postgres_password, last_password_refresh, connection_status
    
    if postgres_password is None or time.time() - last_password_refresh > 900:
        print("Refreshing PostgreSQL OAuth token")
        
        # Initialize Databricks client if not already done
        if workspace_client is None:
            if not initialize_databricks_client():
                return False
        
        try:
            postgres_password = workspace_client.config.oauth_token().access_token
            last_password_refresh = time.time()
            connection_status["status"] = "token_ok"
            connection_status["message"] = "OAuth token refreshed successfully"
            print("✅ OAuth token refreshed successfully")
            return True
        except Exception as e:
            connection_status["status"] = "token_error"
            connection_status["message"] = f"Failed to refresh OAuth token: {str(e)}"
            print(f"❌ Failed to refresh OAuth token: {str(e)}")
            print("💡 Try running: databricks auth login")
            return False
    return True

def get_connection_pool():
    """Get or create the connection pool."""
    global connection_pool, connection_status
    
    if connection_pool is None:
        # Check environment variables
        required_vars = ['PGDATABASE', 'PGUSER', 'PGHOST', 'PGPORT', 'PGSCHEMA']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            connection_status["status"] = "env_error"
            connection_status["message"] = f"Missing environment variables: {', '.join(missing_vars)}"
            print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
            print("💡 Run 'python3 setup_env.py' to configure them")
            return None
        
        if not refresh_oauth_token():
            return None
            
        if not postgres_password:
            connection_status["status"] = "token_error"
            connection_status["message"] = "No OAuth token available"
            return None
        
        try:
            conn_string = (
                f"dbname={os.getenv('PGDATABASE')} "
                f"user={os.getenv('PGUSER')} "
                f"password={postgres_password} "
                f"host={os.getenv('PGHOST')} "
                f"port={os.getenv('PGPORT')} "
                f"sslmode={os.getenv('PGSSLMODE', 'require')} "
                f"application_name={os.getenv('PGAPPNAME')}"
            )
            connection_pool = ConnectionPool(conn_string, min_size=2, max_size=10)
            connection_status["status"] = "connected"
            connection_status["message"] = f"Connected to {os.getenv('PGHOST')}"
            print(f"✅ Database connection pool created for {os.getenv('PGHOST')}")
        except Exception as e:
            connection_status["status"] = "connection_error"
            connection_status["message"] = f"Failed to create connection pool: {str(e)}"
            print(f"❌ Failed to create connection pool: {str(e)}")
            print("💡 Run 'python3 debug_connection.py' to diagnose the issue")
            return None
    
    return connection_pool

def get_connection():
    """Get a connection from the pool."""
    global connection_pool
    
    # Recreate pool if token expired
    if postgres_password is None or time.time() - last_password_refresh > 900:
        if connection_pool:
            connection_pool.close()
            connection_pool = None
    
    pool = get_connection_pool()
    if pool is None:
        return None
    
    try:
        return pool.connection()
    except Exception as e:
        print(f"❌ Failed to get connection from pool: {str(e)}")
        connection_status["status"] = "connection_error"
        connection_status["message"] = f"Failed to get connection: {str(e)}"
        return None

def get_connection_status():
    """Get current connection status for display."""
    return connection_status

def analyze_adverse_event_with_databricks(event_description):
    """Analyze adverse event description using Databricks API."""
    try:
        # Get Databricks token from environment
        databricks_token = os.environ.get('DATABRICKS_TOKEN')
        if not databricks_token:
            return {"error": "DATABRICKS_TOKEN environment variable not set"}
        
        # Initialize OpenAI client with Databricks endpoint
        client = OpenAI(
            api_key=databricks_token,
            base_url="https://e2-demo-field-eng.cloud.databricks.com/serving-endpoints"
        )
        
        # Make API call
        response = client.chat.completions.create(
            model="kie-aaf115b7-endpoint",
            messages=[
                {
                    "role": "user",
                    "content": f"extract root cause, actions to be taken, and affected devices from {event_description}"
                }
            ]
        )
        
        # Parse the response content as JSON if possible
        content = response.choices[0].message.content
        try:
            # Try to parse as JSON first
            parsed_content = json.loads(content)
            return {"success": True, "data": parsed_content}
        except json.JSONDecodeError:
            # If not JSON, return as formatted text
            return {"success": True, "data": {"analysis": content}}
            
    except Exception as e:
        return {"error": f"Failed to analyze adverse event: {str(e)}"}

def get_retailer_orders(retailer_name):
    """Get all orders for a specific retailer."""
    try:
        with get_connection() as conn:
            if conn is None:
                print("❌ Cannot get retailer orders: No database connection")
                return []
            with conn.cursor() as cur:
                schema = os.getenv('PGSCHEMA', 'mma')
                # Optimized query: Remove ORDER BY to avoid sorting millions of records
                # Just get first 100 matches without sorting for speed
                query = f"""
                    SELECT order_id, order_date, device_name, quantity
                    FROM {schema}.synced_order_table_feallstars
                    WHERE LOWER(retailer_name) = LOWER(%s)
                    LIMIT 100
                """
                cur.execute(query, (retailer_name.strip(),))
                results = cur.fetchall()
                
                # Convert to list of dictionaries for easier handling
                orders = []
                for row in results:
                    orders.append({
                        'order_id': row[0],
                        'order_date': row[1],
                        'device_name': row[2],
                        'quantity': row[3]
                    })
                print(f"✅ Found {len(orders)} orders for retailer: {retailer_name}")
                return orders
    except psycopg.Error as e:
        print(f"❌ Database error getting retailer orders: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error getting retailer orders: {e}")
        return []

def get_device_adverse_events(device_names):
    """Get adverse events for a list of device names."""
    if not device_names:
        return {}
    
    try:
        with get_connection() as conn:
            if conn is None:
                print("❌ Cannot get adverse events: No database connection")
                return {}
            with conn.cursor() as cur:
                # Limit device names to prevent parameter overflow (PostgreSQL limit is 65535)
                limited_device_names = device_names[:1000]  # Limit to first 1000 unique devices
                
                # Create placeholders for the IN clause
                placeholders = ','.join(['%s'] * len(limited_device_names))
                schema = os.getenv('PGSCHEMA', 'mma')
                query = f"""
                    SELECT device_name, event_date, adverse_event_description, severity_level
                    FROM {schema}.synced_table_adverse_events
                    WHERE device_name IN ({placeholders})
                    ORDER BY event_date DESC, severity_level
                """
                cur.execute(query, limited_device_names)
                results = cur.fetchall()
                
                # Convert to list of dictionaries grouped by device
                adverse_events = {}
                total_events = 0
                for row in results:
                    device_name = row[0]
                    if device_name not in adverse_events:
                        adverse_events[device_name] = []
                    
                    adverse_events[device_name].append({
                        'event_date': row[1],
                        'adverse_event_description': row[2],
                        'severity_level': row[3]
                    })
                    total_events += 1
                
                print(f"✅ Found {total_events} adverse events for {len(adverse_events)} devices")
                return adverse_events
    except psycopg.Error as e:
        print(f"❌ Database error getting adverse events: {e}")
        return {}
    except Exception as e:
        print(f"❌ Unexpected error getting adverse events: {e}")
        return {}

def get_unique_device_names(orders):
    """Extract unique device names from orders."""
    return list(set([order['device_name'] for order in orders if order['device_name']]))

# Initialize Dash app
app = dash.Dash(__name__)

# Initialize Databricks client at startup
initialize_databricks_client()

# App layout
app.layout = html.Div([
    html.H1("🏥 Medical Device Retailer Order & Adverse Events Tracker",
            style={'textAlign': 'center', 'marginBottom': '30px', 'color': '#2c3e50'}),
    
    # Connection status display
    html.Div(id='connection-status', style={'marginBottom': '20px'}),
    
    # Search section
    html.Div([
        html.H3("🔍 Search Retailer Orders", style={'color': '#34495e'}),
        html.Div([
            dcc.Input(
                id='retailer-name-input',
                type='text',
                placeholder='Enter medical device retailer name...',
                style={
                    'width': '70%', 
                    'padding': '12px', 
                    'marginRight': '10px',
                    'border': '2px solid #bdc3c7',
                    'borderRadius': '5px',
                    'fontSize': '16px'
                }
            ),
            html.Button(
                'Search Orders',
                id='search-button',
                n_clicks=0,
                style={
                    'padding': '12px 24px', 
                    'backgroundColor': '#3498db', 
                    'color': 'white', 
                    'border': 'none', 
                    'borderRadius': '5px',
                    'fontSize': '16px',
                    'cursor': 'pointer'
                }
            )
        ], style={'display': 'flex', 'alignItems': 'center'}),
        html.Div(id='search-message', style={'marginTop': '15px', 'fontSize': '14px'})
    ], style={
        'marginBottom': '30px', 
        'padding': '25px', 
        'backgroundColor': '#ecf0f1', 
        'borderRadius': '10px',
        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
    }),
    
    # Orders section
    html.Div([
        html.H3("📋 Retailer Orders", style={'color': '#34495e', 'marginBottom': '20px'}),
        html.Div(id='orders-container')
    ], style={'marginBottom': '30px'}),
    
    # Adverse events section
    html.Div([
        html.H3("⚠️ Device Adverse Events", style={'color': '#e74c3c', 'marginBottom': '20px'}),
        html.Div(id='adverse-events-container')
    ], style={'marginBottom': '30px'}),
    
    # Adverse event analysis section
    html.Div([
        html.H3("🤖 AI Adverse Event Analysis", style={'color': '#8e44ad', 'marginBottom': '20px'}),
        html.P("Enter an adverse event description to get AI-powered analysis including root cause, recommended actions, and affected devices.",
               style={'color': '#7f8c8d', 'marginBottom': '15px'}),
        html.Div([
            dcc.Textarea(
                id='adverse-event-input',
                placeholder='Enter adverse event description (e.g., "Electric Low Speed Handpiece malfunction during procedure")...',
                style={
                    'width': '100%',
                    'height': '100px',
                    'padding': '12px',
                    'border': '2px solid #bdc3c7',
                    'borderRadius': '5px',
                    'fontSize': '14px',
                    'fontFamily': 'Arial, sans-serif',
                    'resize': 'vertical',
                    'marginBottom': '15px'
                }
            ),
            html.Button(
                'Analyze Event',
                id='analyze-event-button',
                n_clicks=0,
                style={
                    'padding': '12px 24px',
                    'backgroundColor': '#8e44ad',
                    'color': 'white',
                    'border': 'none',
                    'borderRadius': '5px',
                    'fontSize': '16px',
                    'cursor': 'pointer',
                    'marginBottom': '15px'
                }
            )
        ]),
        html.Div(id='analysis-loading', style={'marginBottom': '15px'}),
        html.Div(id='analysis-results-container')
    ], style={
        'marginBottom': '30px',
        'padding': '25px',
        'backgroundColor': '#f8f4ff',
        'borderRadius': '10px',
        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
        'border': '1px solid #d1c4e9'
    }),
    
    # Store components for data management
    dcc.Store(id='orders-store'),
    dcc.Store(id='adverse-events-store'),
    dcc.Store(id='selected-retailer-store'),
    dcc.Store(id='analysis-results-store'),
    dcc.Interval(id='connection-check-interval', interval=30000, n_intervals=0)  # Check every 30 seconds
], style={'maxWidth': '1200px', 'margin': '0 auto', 'padding': '20px'})

@app.callback(
    Output('connection-status', 'children'),
    [Input('connection-check-interval', 'n_intervals')],
    prevent_initial_call=False
)
def update_connection_status(n_intervals):
    """Update the connection status display."""
    status = get_connection_status()
    
    status_colors = {
        'connected': '#27ae60',
        'databricks_ok': '#3498db',
        'token_ok': '#f39c12',
        'not_initialized': '#95a5a6',
        'databricks_error': '#e74c3c',
        'token_error': '#e74c3c',
        'env_error': '#e74c3c',
        'connection_error': '#e74c3c'
    }
    
    status_icons = {
        'connected': '✅',
        'databricks_ok': '🔄',
        'token_ok': '🔑',
        'not_initialized': '⏳',
        'databricks_error': '❌',
        'token_error': '❌',
        'env_error': '❌',
        'connection_error': '❌'
    }
    
    color = status_colors.get(status['status'], '#95a5a6')
    icon = status_icons.get(status['status'], '❓')
    
    return html.Div([
        html.Span(f"{icon} Database Status: ", style={'fontWeight': 'bold'}),
        html.Span(status['message'], style={'color': color})
    ], style={
        'padding': '10px',
        'backgroundColor': '#f8f9fa',
        'border': f'1px solid {color}',
        'borderRadius': '5px',
        'textAlign': 'center'
    })

@app.callback(
    [Output('orders-store', 'data'),
     Output('selected-retailer-store', 'data'),
     Output('search-message', 'children')],
    [Input('search-button', 'n_clicks'),
     Input('retailer-name-input', 'n_submit')],
    [State('retailer-name-input', 'value')],
    prevent_initial_call=True
)
def search_retailer_orders(search_clicks, submit_clicks, retailer_name):
    """Search for orders by retailer name."""
    if not retailer_name or not retailer_name.strip():
        return [], None, html.Div("Please enter a retailer name.", style={'color': '#e74c3c'})
    
    orders = get_retailer_orders(retailer_name.strip())
    
    if not orders:
        message = html.Div(f"No orders found for retailer: {retailer_name}", 
                          style={'color': '#f39c12'})
        return [], retailer_name.strip(), message
    
    message = html.Div(f"Found {len(orders)} orders for {retailer_name}", 
                      style={'color': '#27ae60'})
    return orders, retailer_name.strip(), message

@app.callback(
    Output('adverse-events-store', 'data'),
    [Input('orders-store', 'data')],
    prevent_initial_call=True
)
def load_adverse_events(orders_data):
    """Load adverse events for devices in the orders."""
    if not orders_data:
        return {}
    
    device_names = get_unique_device_names(orders_data)
    adverse_events = get_device_adverse_events(device_names)
    return adverse_events

@app.callback(
    Output('orders-container', 'children'),
    [Input('orders-store', 'data')],
    prevent_initial_call=True
)
def display_orders(orders_data):
    """Display the orders table."""
    if not orders_data:
        return html.Div("No orders to display.", 
                       style={'textAlign': 'center', 'color': '#7f8c8d', 'fontStyle': 'italic'})
    
    # Convert to DataFrame for dash_table
    df = pd.DataFrame(orders_data)
    df['order_date'] = pd.to_datetime(df['order_date']).dt.strftime('%Y-%m-%d')
    
    return dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[
            {'name': 'Order ID', 'id': 'order_id', 'type': 'numeric'},
            {'name': 'Order Date', 'id': 'order_date', 'type': 'datetime'},
            {'name': 'Device Name', 'id': 'device_name', 'type': 'text'},
            {'name': 'Quantity', 'id': 'quantity', 'type': 'numeric'}
        ],
        style_cell={
            'textAlign': 'left',
            'padding': '12px',
            'fontFamily': 'Arial, sans-serif'
        },
        style_header={
            'backgroundColor': '#34495e',
            'color': 'white',
            'fontWeight': 'bold'
        },
        style_data={
            'backgroundColor': '#ffffff',
            'border': '1px solid #bdc3c7'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#f8f9fa'
            }
        ],
        sort_action='native',
        page_size=10
    )

@app.callback(
    Output('adverse-events-container', 'children'),
    [Input('adverse-events-store', 'data')],
    prevent_initial_call=True
)
def display_adverse_events(adverse_events_data):
    """Display adverse events with dropdowns for each device."""
    if not adverse_events_data:
        return html.Div("No adverse events found for the ordered devices.", 
                       style={'textAlign': 'center', 'color': '#7f8c8d', 'fontStyle': 'italic'})
    
    device_sections = []
    
    for device_name, events in adverse_events_data.items():
        if not events:
            continue
            
        # Create dropdown options
        dropdown_options = []
        for i, event in enumerate(events):
            severity_color = {
                'High': '🔴',
                'Medium': '🟡', 
                'Low': '🟢'
            }.get(event['severity_level'], '⚪')
            
            option_label = f"{severity_color} {event['event_date']} - {event['adverse_event_description'][:50]}..."
            dropdown_options.append({
                'label': option_label,
                'value': i
            })
        
        device_section = html.Div([
            html.H4(f"📱 {device_name}", 
                   style={'color': '#2c3e50', 'marginBottom': '10px'}),
            html.P(f"Found {len(events)} adverse event(s)", 
                  style={'color': '#7f8c8d', 'fontSize': '14px', 'marginBottom': '10px'}),
            dcc.Dropdown(
                id={'type': 'adverse-event-dropdown', 'device': device_name},
                options=dropdown_options,
                placeholder="Select an adverse event to view details...",
                style={'marginBottom': '10px'}
            ),
            html.Div(id={'type': 'adverse-event-details', 'device': device_name})
        ], style={
            'marginBottom': '25px',
            'padding': '20px',
            'backgroundColor': '#fff5f5',
            'border': '1px solid #fed7d7',
            'borderRadius': '8px'
        })
        
        device_sections.append(device_section)
    
    return device_sections

@app.callback(
    Output({'type': 'adverse-event-details', 'device': dash.MATCH}, 'children'),
    [Input({'type': 'adverse-event-dropdown', 'device': dash.MATCH}, 'value')],
    [State('adverse-events-store', 'data'),
     State({'type': 'adverse-event-dropdown', 'device': dash.MATCH}, 'id')],
    prevent_initial_call=True
)
def display_adverse_event_details(selected_event_index, adverse_events_data, dropdown_id):
    """Display detailed information for the selected adverse event."""
    if selected_event_index is None or not adverse_events_data:
        return ""
    
    device_name = dropdown_id['device']
    events = adverse_events_data.get(device_name, [])
    
    if selected_event_index >= len(events):
        return ""
    
    event = events[selected_event_index]
    
    severity_style = {
        'High': {'backgroundColor': '#fee', 'color': '#c53030', 'border': '1px solid #feb2b2'},
        'Medium': {'backgroundColor': '#fffbeb', 'color': '#d69e2e', 'border': '1px solid #fbd38d'},
        'Low': {'backgroundColor': '#f0fff4', 'color': '#38a169', 'border': '1px solid #9ae6b4'}
    }.get(event['severity_level'], {'backgroundColor': '#f7fafc', 'color': '#4a5568', 'border': '1px solid #e2e8f0'})
    
    return html.Div([
        html.Div([
            html.Strong("Event Date: "),
            html.Span(str(event['event_date']))
        ], style={'marginBottom': '10px'}),
        html.Div([
            html.Strong("Severity Level: "),
            html.Span(event['severity_level'], 
                     style={
                         'padding': '4px 8px',
                         'borderRadius': '4px',
                         'fontWeight': 'bold',
                         **severity_style
                     })
        ], style={'marginBottom': '10px'}),
        html.Div([
            html.Strong("Event Description: "),
            html.P(event['adverse_event_description'], 
                  style={'marginTop': '5px', 'lineHeight': '1.5'})
        ])
    ], style={
        'padding': '15px',
        'backgroundColor': '#ffffff',
        'border': '1px solid #e2e8f0',
        'borderRadius': '6px',
        'marginTop': '10px'
    })

@app.callback(
    [Output('analysis-results-store', 'data'),
     Output('analysis-loading', 'children')],
    [Input('analyze-event-button', 'n_clicks')],
    [State('adverse-event-input', 'value')],
    prevent_initial_call=True
)
def analyze_adverse_event(n_clicks, event_description):
    """Analyze adverse event description using Databricks API."""
    if not event_description or not event_description.strip():
        return None, html.Div("Please enter an adverse event description.",
                             style={'color': '#e74c3c', 'fontStyle': 'italic'})
    
    # Show loading message
    loading_message = html.Div([
        html.Span("🔄 Analyzing adverse event with AI... ", style={'marginRight': '10px'}),
        html.Span("This may take a few seconds.", style={'fontStyle': 'italic', 'color': '#7f8c8d'})
    ], style={'color': '#3498db', 'fontWeight': 'bold'})
    
    # Call the analysis function
    result = analyze_adverse_event_with_databricks(event_description.strip())
    
    if 'error' in result:
        error_message = html.Div(f"❌ Error: {result['error']}",
                                style={'color': '#e74c3c', 'fontWeight': 'bold'})
        return None, error_message
    
    success_message = html.Div("✅ Analysis completed successfully!",
                              style={'color': '#27ae60', 'fontWeight': 'bold'})
    return result, success_message

@app.callback(
    Output('analysis-results-container', 'children'),
    [Input('analysis-results-store', 'data')],
    prevent_initial_call=True
)
def display_analysis_results(analysis_data):
    """Display the formatted analysis results."""
    if not analysis_data or not analysis_data.get('success'):
        return ""
    
    data = analysis_data.get('data', {})
    
    # If data is a simple dict with 'analysis' key (text response)
    if 'analysis' in data and len(data) == 1:
        return html.Div([
            html.H4("📊 Analysis Results", style={'color': '#8e44ad', 'marginBottom': '15px'}),
            html.Div([
                html.Pre(data['analysis'], style={
                    'whiteSpace': 'pre-wrap',
                    'backgroundColor': '#f8f9fa',
                    'padding': '15px',
                    'borderRadius': '5px',
                    'border': '1px solid #e9ecef',
                    'fontFamily': 'Arial, sans-serif',
                    'fontSize': '14px',
                    'lineHeight': '1.5'
                })
            ])
        ], style={
            'padding': '20px',
            'backgroundColor': '#ffffff',
            'border': '1px solid #d1c4e9',
            'borderRadius': '8px',
            'marginTop': '10px'
        })
    
    # If data is structured JSON
    else:
        components = []
        components.append(html.H4("📊 Analysis Results", style={'color': '#8e44ad', 'marginBottom': '15px'}))
        
        # Display each key-value pair in the JSON
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                # Format complex objects as JSON
                formatted_value = json.dumps(value, indent=2)
                components.append(html.Div([
                    html.Strong(f"{key.replace('_', ' ').title()}: ", style={'color': '#2c3e50'}),
                    html.Pre(formatted_value, style={
                        'backgroundColor': '#f8f9fa',
                        'padding': '10px',
                        'borderRadius': '4px',
                        'border': '1px solid #e9ecef',
                        'marginTop': '5px',
                        'fontSize': '12px',
                        'fontFamily': 'monospace'
                    })
                ], style={'marginBottom': '15px'}))
            else:
                # Display simple values
                components.append(html.Div([
                    html.Strong(f"{key.replace('_', ' ').title()}: ", style={'color': '#2c3e50'}),
                    html.Span(str(value))
                ], style={'marginBottom': '10px'}))
        
        return html.Div(components, style={
            'padding': '20px',
            'backgroundColor': '#ffffff',
            'border': '1px solid #d1c4e9',
            'borderRadius': '8px',
            'marginTop': '10px'
        })

if __name__ == '__main__':
    app.run(debug=True)
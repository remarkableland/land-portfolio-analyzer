import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
from io import BytesIO
import requests
import time
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

st.set_page_config(
    page_title="Land Portfolio Analyzer",
    page_icon="🏞️",
    layout="wide"
)

# Close.com API Configuration
# NOTE: This API key appears to be invalid (401 Unauthorized error)
# You'll need to get a valid API key from Close.com
CLOSE_API_KEY = "api_74RFzgOQpU0hdtf3tHZyWK.4OlJ6xHkGeq8ez1ZkJApdP"
CLOSE_API_BASE = "https://api.close.com/api/v1"

# Add API key input in sidebar for easy updating
def get_api_key():
    """Get API key from sidebar input or use default"""
    with st.sidebar:
        st.subheader("🔑 Close.com API Configuration")
        api_key = st.text_input(
            "Close.com API Key", 
            value=CLOSE_API_KEY,
            type="password",
            help="Enter your Close.com API key. Get it from Close.com Settings > API Keys"
        )
        if api_key != CLOSE_API_KEY:
            st.info("✅ Using custom API key")
        else:
            st.warning("⚠️ Using default API key (may be invalid)")
        
        # Show API key info for debugging
        if api_key:
            st.write(f"**API Key Info:**")
            st.write(f"- Length: {len(api_key)} characters")
            st.write(f"- Starts with: `{api_key[:10]}...`")
            st.write(f"- Format: {'✅ Looks like Close.com format' if api_key.startswith('api_') else '❓ Unusual format'}")
        
        st.markdown("""
        **How to get your API key:**
        1. Log in to Close.com
        2. Go to Settings > API Keys
        3. Create a new API key with **READ permissions for Leads**
        4. Copy and paste it above
        
        **Important:** Make sure your API key has:
        - ✅ Read access to Leads
        - ✅ Correct organization scope
        """)
    return api_key

def query_close_leads_by_apn(apn):
    """Query Close.com for leads matching specific APN"""
    if pd.isna(apn) or apn == '' or str(apn).strip() == '':
        return {"count": 0, "status": "No APN", "debug": "Empty APN"}
    
    api_key = get_api_key()
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Clean the APN for the search query
        clean_apn = str(apn).strip()
        
        # Handle multiple APNs separated by commas
        apn_list = [apn.strip() for apn in clean_apn.split(',')]
        
        all_leads = []
        search_attempts = []
        
        # Try searching for each individual APN
        for individual_apn in apn_list:
            if individual_apn:  # Skip empty strings
                # Try multiple search strategies
                search_queries = [
                    f'custom.All_APN:"{individual_apn}"',  # Exact match in quotes
                    f'custom.All_APN:{individual_apn}',    # Without quotes
                    f'"{individual_apn}"',                 # Global search with quotes
                    individual_apn                         # Simple global search
                ]
                
                for query in search_queries:
                    try:
                        response = requests.get(
                            f"{CLOSE_API_BASE}/lead/",
                            headers=headers,
                            params={
                                "query": query,
                                "_limit": 100
                            },
                            timeout=10
                        )
                        
                        # Handle authentication errors
                        if response.status_code == 401:
                            return {
                                "count": 0,
                                "status": "Auth Error",
                                "debug": {
                                    "error": "401 Unauthorized - Invalid API key",
                                    "message": "Please update your Close.com API key in the sidebar"
                                }
                            }
                        
                        response.raise_for_status()
                        data = response.json()
                        leads = data.get("data", [])
                        
                        search_attempts.append({
                            "apn": individual_apn,
                            "query": query,
                            "leads_found": len(leads),
                            "http_status": response.status_code
                        })
                        
                        # If we found leads with this query, add them and stop trying other queries for this APN
                        if leads:
                            all_leads.extend(leads)
                            break
                            
                    except Exception as search_error:
                        search_attempts.append({
                            "apn": individual_apn,
                            "query": query,
                            "error": str(search_error)[:50]
                        })
                        continue
        
        # Remove duplicates (in case same lead matched multiple APNs)
        unique_leads = []
        seen_lead_ids = set()
        for lead in all_leads:
            lead_id = lead.get('id', '')
            if lead_id and lead_id not in seen_lead_ids:
                unique_leads.append(lead)
                seen_lead_ids.add(lead_id)
        
        # DEBUG: Show what we found
        debug_info = {
            "original_apn": clean_apn,
            "apn_list": apn_list,
            "search_attempts": search_attempts,
            "total_leads_found": len(unique_leads),
            "unique_lead_ids": len(seen_lead_ids)
        }
        
        # If we found leads, let's see their structure
        if unique_leads and len(unique_leads) > 0:
            first_lead = unique_leads[0]
            debug_info["first_lead_keys"] = list(first_lead.keys()) if isinstance(first_lead, dict) else "Not a dict"
            debug_info["first_lead_status"] = first_lead.get("status_label", "NO STATUS FIELD")
            # Check if the lead actually has the APN field
            debug_info["first_lead_has_apn"] = "custom.All_APN" in first_lead
            debug_info["first_lead_apn_value"] = first_lead.get("custom.All_APN", "NO APN FIELD")
        
        # Filter OUT leads with excluded statuses
        excluded_statuses = ["Remarkable Asset", "Remarkable Sold", "Neighbor"]
        filtered_leads = []
        
        for lead in unique_leads:
            lead_status = lead.get("status_label", "")
            if lead_status not in excluded_statuses:
                filtered_leads.append(lead)
        
        status = "Success" if len(search_attempts) > 0 else "No searches attempted"
        
        return {
            "count": len(filtered_leads),
            "status": status,
            "total_leads": len(unique_leads),
            "filtered_leads": len(filtered_leads),
            "debug": debug_info
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "count": 0, 
            "status": f"API Error: {str(e)[:50]}", 
            "debug": {
                "error_type": "RequestException",
                "error_message": str(e),
                "original_apn": str(apn)
            }
        }
    except Exception as e:
        return {
            "count": 0, 
            "status": f"Error: {str(e)[:50]}", 
            "debug": {
                "error_type": "General Exception",
                "error_message": str(e),
                "original_apn": str(apn)
            }
        }

def test_close_api_connection():
    """Test Close.com API connection and show available fields"""
    api_key = get_api_key()
    
    # Try different authentication methods
    auth_methods = [
        ("Bearer", f"Bearer {api_key}"),
        ("Basic", api_key),  # Some APIs use basic auth with just the key
        ("API-Key", api_key),  # Some APIs use custom headers
    ]
    
    for auth_type, auth_value in auth_methods:
        try:
            headers = {
                "Authorization": auth_value,
                "Content-Type": "application/json"
            }
            
            st.write(f"🔍 Trying authentication method: {auth_type}")
            
            # Get a few leads to see their structure
            response = requests.get(
                f"{CLOSE_API_BASE}/lead/",
                headers=headers,
                params={"_limit": 5},  # Just get 5 leads to examine
                timeout=10
            )
            
            st.write(f"📊 Response status: {response.status_code}")
            
            # If this method works, use it
            if response.status_code == 200:
                st.success(f"✅ Authentication successful with {auth_type} method!")
                
                data = response.json()
                leads = data.get("data", [])
                
                if leads:
                    first_lead = leads[0]
                    
                    # Look for APN-related fields
                    apn_fields = []
                    for key in first_lead.keys():
                        if 'apn' in key.lower() or 'APN' in key:
                            apn_fields.append(key)
                    
                    # Also check custom fields
                    custom_fields = []
                    for key in first_lead.keys():
                        if key.startswith('custom.'):
                            custom_fields.append(key)
                    
                    return {
                        "success": True,
                        "auth_method": auth_type,
                        "total_leads_in_system": len(leads),
                        "sample_lead_keys": list(first_lead.keys()),
                        "apn_related_fields": apn_fields,
                        "custom_fields": custom_fields,
                        "first_lead_sample": {k: v for k, v in first_lead.items() if k in ['name', 'status_label'] + apn_fields[:3]}
                    }
                else:
                    return {
                        "success": True,
                        "auth_method": auth_type,
                        "total_leads_in_system": 0,
                        "message": "Authentication successful but no leads found in system"
                    }
            
            elif response.status_code == 401:
                st.warning(f"❌ {auth_type} authentication failed: 401 Unauthorized")
                continue
            else:
                st.warning(f"❌ {auth_type} failed with status: {response.status_code}")
                continue
                
        except Exception as e:
            st.warning(f"❌ {auth_type} method error: {str(e)}")
            continue
    
    # If all methods failed
    return {
        "success": False,
        "error": "All authentication methods failed",
        "message": "Please verify your API key and permissions",
        "tried_methods": [method[0] for method in auth_methods],
        "instructions": [
            "1. Verify the API key is correct",
            "2. Check that the API key has 'read' permissions for leads",
            "3. Make sure the API key is for the correct Close.com organization",
            "4. Try regenerating the API key in Close.com settings"
        ]
    }

def process_lead_counts(df):
    """Add lead count data from Close.com to the dataframe"""
    # Initialize lead count column
    df['lead_count'] = 0
    df['lead_query_status'] = "Not processed"
    
    # Only process rows that have APN values
    apn_rows = df[df['custom.All_APN'].notna() & 
                  (df['custom.All_APN'] != '') & 
                  (df['custom.All_APN'].astype(str).str.strip() != '')].index
    
    if len(apn_rows) > 0:
        st.info(f"🔍 Querying Close.com for lead data on {len(apn_rows)} properties...")
        st.info("📊 Filtering out statuses: 'Remarkable Asset', 'Remarkable Sold', 'Neighbor'")
        
        # Add API connection test button for debugging
        if st.button("🔧 Test Close.com API Connection", help="Click to test the API and see available fields"):
            with st.expander("API Connection Test Results", expanded=True):
                test_result = test_close_api_connection()
                st.json(test_result)
        
        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        
        success_count = 0
        total_leads_found = 0
        debug_details = []
        
        for i, idx in enumerate(apn_rows):
            apn = df.loc[idx, 'custom.All_APN']
            property_name = df.loc[idx, 'display_name'] if 'display_name' in df.columns else f"Property {idx}"
            
            # Update progress
            progress = (i + 1) / len(apn_rows)
            progress_bar.progress(progress)
            status_placeholder.text(f"Processing {property_name[:30]}... ({i+1}/{len(apn_rows)})")
            
            # Query Close.com
            lead_data = query_close_leads_by_apn(apn)
            
            # Store debug info for first few properties
            if i < 5:  # Debug first 5 properties instead of 3
                debug_details.append({
                    "property": property_name,
                    "apn": apn,
                    "query_result": lead_data
                })
            
            # Update dataframe
            df.loc[idx, 'lead_count'] = lead_data['count']
            df.loc[idx, 'lead_query_status'] = lead_data['status']
            
            if lead_data['status'] == 'Success':
                success_count += 1
                total_leads_found += lead_data['count']
            
            # Add small delay to be respectful to the API
            time.sleep(0.1)
        
        progress_bar.empty()
        status_placeholder.empty()
        
        # Show summary
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Properties Queried", f"{success_count}/{len(apn_rows)}")
        with col2:
            st.metric("Total Qualified Leads", total_leads_found)
        with col3:
            avg_leads = total_leads_found / len(apn_rows) if len(apn_rows) > 0 else 0
            st.metric("Avg Leads/Property", f"{avg_leads:.1f}")
        
        if success_count < len(apn_rows):
            st.warning(f"⚠️ {len(apn_rows) - success_count} properties had API query issues.")
        
        # Show debugging information
        if debug_details:
            st.subheader("🔧 Debugging Information (First 5 Properties)")
            for detail in debug_details:
                with st.expander(f"Debug: {detail['property']} (APN: {detail['apn']})"):
                    st.json(detail['query_result'])
        
        # Show sample APN values for debugging
        st.subheader("📋 Sample APN Values from CSV")
        sample_apns = df.loc[apn_rows[:10], 'custom.All_APN'].tolist()
        st.write("First 10 APNs from your data:")
        for i, apn in enumerate(sample_apns, 1):
            st.write(f"{i}. `{apn}` (type: {type(apn)}, length: {len(str(apn))})")
            
    else:
        st.info("ℹ️ No properties with APN values found to query.")
        df['lead_count'] = 0
        df['lead_query_status'] = "No APN"
    
    return df

def calculate_days_on_market(row):
    """Calculate days on market from MLS listing date"""
    try:
        listing_date = row.get('custom.Asset_MLS_Listing_Date')
        if pd.isna(listing_date):
            return None
        
        listing_dt = pd.to_datetime(listing_date)
        return (datetime.now() - listing_dt).days
    except:
        return None

def check_missing_information(row):
    """Check for missing required fields and return status"""
    required_fields = {
        'custom.All_APN': 'APN',
        'custom.All_Asset_Surveyed_Acres': 'Surveyed Acres',
        'custom.All_County': 'County',
        'custom.All_RemarkableLand_URL': 'RemarkableLand URL',
        'custom.All_State': 'State',
        'custom.Asset_Cost_Basis': 'Cost Basis',
        'custom.Asset_Date_Purchased': 'Date Purchased',
        'custom.Asset_Original_Listing_Price': 'Original Listing Price',
        'custom.Asset_Land_ID_Internal_URL': 'Land ID Internal URL',
        'custom.Asset_Land_ID_Share_URL': 'Land ID Share URL',
        'custom.Asset_MLS#': 'MLS#',
        'custom.Asset_MLS_Listing_Date': 'MLS Listing Date',
        'custom.Asset_Street_Address': 'Street Address',
        'custom.Asset_Last_Mapping_Audit': 'Last Map Audit',
        'avg_one_time_active_opportunity_value': 'Avg One Time Active Opportunity Value'
    }
    
    missing_fields = []
    
    for field_key, field_name in required_fields.items():
        if field_key in row.index:
            value = row[field_key]
            if pd.isna(value) or value == '' or value == 'Unknown' or value == 'Unknown County':
                missing_fields.append(field_name)
        else:
            missing_fields.append(field_name)
    
    if not missing_fields:
        return "✅ Complete"
    else:
        return "❌ Missing: " + ", ".join(missing_fields)

def process_data(df):
    """Process and clean the uploaded data"""
    try:
        processed_df = df.copy()
        
        # Clean and standardize data
        if 'custom.All_County' in processed_df.columns:
            processed_df['custom.All_County'] = processed_df['custom.All_County'].fillna('Unknown County')
            processed_df['custom.All_County'] = processed_df['custom.All_County'].astype(str).str.title()
        
        # Calculate days on market first
        processed_df['days_on_market'] = processed_df.apply(calculate_days_on_market, axis=1)
        
        # Convert key numeric columns to ensure proper data types
        numeric_columns = [
            'primary_opportunity_value',
            'custom.Asset_Cost_Basis', 
            'custom.All_Asset_Surveyed_Acres',
            'custom.Asset_Original_Listing_Price'
        ]
        
        for col in numeric_columns:
            if col in processed_df.columns:
                processed_df[col] = pd.to_numeric(processed_df[col], errors='coerce').fillna(0)
        
        # Calculate metrics with better error handling
        processed_df['price_reductions'] = 0  # Default value
        if 'primary_opportunity_value' in processed_df.columns:
            try:
                # Ensure the function is properly called
                def calc_price_reductions(price):
                    try:
                        if pd.isna(price) or price == 0:
                            return 0
                        trailing_digit = int(str(int(price))[-1])
                        reduction_map = {9: 0, 8: 1, 7: 2, 6: 3, 5: 4, 4: 5, 3: 6, 2: 7, 1: 8, 0: 9}
                        return reduction_map.get(trailing_digit, 0)
                    except:
                        return 0
                
                processed_df['price_reductions'] = processed_df['primary_opportunity_value'].apply(calc_price_reductions)
            except Exception as e:
                st.warning(f"Could not calculate price reductions: {str(e)}")
                processed_df['price_reductions'] = 0
        
        # Financial calculations with better error handling
        processed_df['current_margin'] = 0
        processed_df['current_margin_pct'] = 0
        if all(col in processed_df.columns for col in ['primary_opportunity_value', 'custom.Asset_Cost_Basis']):
            try:
                processed_df['current_margin'] = processed_df['primary_opportunity_value'] - processed_df['custom.Asset_Cost_Basis']
                # Avoid division by zero
                mask = processed_df['primary_opportunity_value'] != 0
                processed_df.loc[mask, 'current_margin_pct'] = (processed_df.loc[mask, 'current_margin'] / processed_df.loc[mask, 'primary_opportunity_value'] * 100)
            except Exception as e:
                st.warning(f"Could not calculate financial metrics: {str(e)}")
                processed_df['current_margin'] = 0
                processed_df['current_margin_pct'] = 0
        
        # Price per acre with better error handling
        processed_df['price_per_acre'] = 0
        if all(col in processed_df.columns for col in ['primary_opportunity_value', 'custom.All_Asset_Surveyed_Acres']):
            try:
                # Avoid division by zero
                mask = processed_df['custom.All_Asset_Surveyed_Acres'] != 0
                processed_df.loc[mask, 'price_per_acre'] = processed_df.loc[mask, 'primary_opportunity_value'] / processed_df.loc[mask, 'custom.All_Asset_Surveyed_Acres']
            except Exception as e:
                st.warning(f"Could not calculate price per acre: {str(e)}")
                processed_df['price_per_acre'] = 0
        
        # Calculate markup percentage with better error handling
        processed_df['markup_percentage'] = 0
        if all(col in processed_df.columns for col in ['primary_opportunity_value', 'custom.Asset_Cost_Basis']):
            try:
                # Avoid division by zero
                mask = processed_df['custom.Asset_Cost_Basis'] != 0
                processed_df.loc[mask, 'markup_percentage'] = ((processed_df.loc[mask, 'primary_opportunity_value'] - processed_df.loc[mask, 'custom.Asset_Cost_Basis']) / 
                                                              processed_df.loc[mask, 'custom.Asset_Cost_Basis'] * 100)
            except Exception as e:
                st.warning(f"Could not calculate markup percentage: {str(e)}")
                processed_df['markup_percentage'] = 0
        
        # Calculate cost basis per acre with better error handling
        processed_df['cost_basis_per_acre'] = 0
        if all(col in processed_df.columns for col in ['custom.Asset_Cost_Basis', 'custom.All_Asset_Surveyed_Acres']):
            try:
                # Avoid division by zero
                mask = processed_df['custom.All_Asset_Surveyed_Acres'] != 0
                processed_df.loc[mask, 'cost_basis_per_acre'] = processed_df.loc[mask, 'custom.Asset_Cost_Basis'] / processed_df.loc[mask, 'custom.All_Asset_Surveyed_Acres']
            except Exception as e:
                st.warning(f"Could not calculate cost basis per acre: {str(e)}")
                processed_df['cost_basis_per_acre'] = 0
        
        # Calculate percent of original listing price with better error handling
        processed_df['percent_of_initial_listing'] = 0
        if all(col in processed_df.columns for col in ['primary_opportunity_value', 'custom.Asset_Original_Listing_Price']):
            try:
                # Avoid division by zero
                mask = processed_df['custom.Asset_Original_Listing_Price'] != 0
                processed_df.loc[mask, 'percent_of_initial_listing'] = (processed_df.loc[mask, 'primary_opportunity_value'] / 
                                                                       processed_df.loc[mask, 'custom.Asset_Original_Listing_Price'] * 100)
            except Exception as e:
                st.warning(f"Could not calculate percent of initial listing: {str(e)}")
                processed_df['percent_of_initial_listing'] = 0
        
        # Check missing information for each property
        processed_df['missing_information'] = processed_df.apply(check_missing_information, axis=1)
        
        # Process Close.com lead counts
        try:
            processed_df = process_lead_counts(processed_df)
        except Exception as e:
            st.warning(f"Could not process Close.com lead data: {str(e)}")
            processed_df['lead_count'] = 0
            processed_df['lead_query_status'] = "Error"
        
        return processed_df
        
    except Exception as e:
        st.error(f"Error in process_data: {str(e)}")
        # Return basic dataframe with minimal processing
        basic_df = df.copy()
        basic_df['days_on_market'] = None
        basic_df['price_reductions'] = 0
        basic_df['current_margin'] = 0
        basic_df['current_margin_pct'] = 0
        basic_df['price_per_acre'] = 0
        basic_df['markup_percentage'] = 0
        basic_df['cost_basis_per_acre'] = 0
        basic_df['percent_of_initial_listing'] = 0
        basic_df['missing_information'] = "Error processing"
        basic_df['lead_count'] = 0
        basic_df['lead_query_status'] = "Error"
        return basic_df

def display_hierarchy_breakdown(df):
    """Display the Status → State → County hierarchy with correct order"""
    st.header("📊 Portfolio Hierarchy: Status → State → County")
    
    # Overall metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Properties", len(df))
    
    with col2:
        if 'primary_opportunity_value' in df.columns:
            total_value = df['primary_opportunity_value'].sum()
            st.metric("Portfolio Value", f"${total_value:,.0f}")
    
    with col3:
        if 'custom.Asset_Cost_Basis' in df.columns:
            total_cost = df['custom.Asset_Cost_Basis'].sum()
            st.metric("Total Cost Basis", f"${total_cost:,.0f}")
    
    with col4:
        if 'missing_information' in df.columns:
            complete_count = len(df[df['missing_information'] == '✅ Complete'])
            completion_rate = (complete_count / len(df)) * 100
            st.metric("Data Complete", f"{complete_count}/{len(df)} ({completion_rate:.0f}%)")
    
    st.divider()
    
    # Hierarchical breakdown with CORRECT ORDER
    if 'primary_opportunity_status_label' in df.columns:
        status_order = ['Purchased', 'Listed', 'Under Contract']
        available_statuses = df['primary_opportunity_status_label'].unique()
        ordered_statuses = [status for status in status_order if status in available_statuses]
        
        # Level 1: By Status (in correct order)
        st.subheader("🎯 Level 1: By Opportunity Status")
        
        status_summary = []
        for status in ordered_statuses:
            if pd.notna(status):
                status_df = df[df['primary_opportunity_status_label'] == status]
                summary = {
                    'Status': status,
                    'Properties': len(status_df),
                    'Total Value': f"${status_df['primary_opportunity_value'].sum():,.0f}" if 'primary_opportunity_value' in df.columns else 'N/A',
                    'Avg DOM': f"{status_df['days_on_market'].mean():.0f}" if 'days_on_market' in status_df.columns and status_df['days_on_market'].notna().any() else 'N/A',
                    'Avg Reductions': f"{status_df['price_reductions'].mean():.1f}" if 'price_reductions' in status_df.columns and status_df['price_reductions'].notna().any() else 'N/A'
                }
                status_summary.append(summary)
        
        if status_summary:
            st.dataframe(pd.DataFrame(status_summary), use_container_width=True)
        
        # Level 2 & 3: Expandable State and County breakdown
        for status in ordered_statuses:
            if pd.notna(status):
                status_df = df[df['primary_opportunity_status_label'] == status]
                
                with st.expander(f"📋 {status} ({len(status_df)} properties) - State & County Breakdown"):
                    
                    if 'custom.All_State' in status_df.columns:
                        st.write("**Level 2: By State**")
                        
                        for state in sorted(status_df['custom.All_State'].unique()):
                            if pd.notna(state):
                                state_df = status_df[status_df['custom.All_State'] == state]
                                
                                complete_count = len(state_df[state_df['missing_information'] == '✅ Complete'])
                                incomplete_count = len(state_df) - complete_count
                                
                                st.write(f"**{state}** ({len(state_df)} properties | ✅ {complete_count} complete | ❌ {incomplete_count} incomplete)")
                                
                                if 'custom.All_County' in state_df.columns:
                                    county_summary = []
                                    for county in sorted(state_df['custom.All_County'].unique()):
                                        if pd.notna(county):
                                            county_df = state_df[state_df['custom.All_County'] == county]
                                            complete_county = len(county_df[county_df['missing_information'] == '✅ Complete'])
                                            incomplete_county = len(county_df) - complete_county
                                            
                                            county_summary.append({
                                                'County': county,
                                                'Properties': len(county_df),
                                                'Complete': f"✅ {complete_county}",
                                                'Incomplete': f"❌ {incomplete_county}" if incomplete_county > 0 else "✅ 0",
                                                'Total Value': f"${county_df['primary_opportunity_value'].sum():,.0f}" if 'primary_opportunity_value' in county_df.columns else 'N/A',
                                                'Avg Acres': f"{county_df['custom.All_Asset_Surveyed_Acres'].mean():.1f}" if 'custom.All_Asset_Surveyed_Acres' in county_df.columns else 'N/A'
                                            })
                                    
                                    if county_summary:
                                        st.dataframe(pd.DataFrame(county_summary), use_container_width=True)

def create_visualizations(df):
    """Create portfolio visualizations with correct status order"""
    st.header("📈 Portfolio Visualizations")
    
    col1, col2 = st.columns(2)
    
    # Status distribution
    with col1:
        if 'primary_opportunity_status_label' in df.columns:
            st.subheader("Distribution by Status")
            
            status_order = ['Purchased', 'Listed', 'Under Contract']
            status_counts = df['primary_opportunity_status_label'].value_counts()
            
            ordered_labels = []
            ordered_values = []
            for status in status_order:
                if status in status_counts.index:
                    ordered_labels.append(status)
                    ordered_values.append(status_counts[status])
            
            fig = px.pie(values=ordered_values, names=ordered_labels,
                        color_discrete_sequence=['#2E8B57', '#4169E1', '#FF6347'])
            st.plotly_chart(fig, use_container_width=True)
    
    # State distribution
    with col2:
        if 'custom.All_State' in df.columns:
            st.subheader("Distribution by State")
            state_counts = df['custom.All_State'].value_counts()
            fig = px.bar(x=state_counts.index, y=state_counts.values, 
                        labels={'x': 'State', 'y': 'Properties'},
                        color=state_counts.values,
                        color_continuous_scale='viridis')
            st.plotly_chart(fig, use_container_width=True)

def generate_missing_fields_checklist_pdf(df):
    """Generate a super compact PDF checklist of missing fields for each property"""
    if not REPORTLAB_AVAILABLE:
        st.error("PDF generation requires reportlab. Please install it: pip install reportlab")
        return None
    
    # Create a BytesIO buffer for the PDF
    buffer = BytesIO()
    
    # Create the PDF document with very tight margins
    doc = SimpleDocTemplate(buffer, pagesize=letter, 
                          topMargin=0.4*inch, bottomMargin=0.4*inch,
                          leftMargin=0.4*inch, rightMargin=0.4*inch)
    story = []
    
    # Get styles and create super compact styles
    styles = getSampleStyleSheet()
    
    # Super compact title style
    title_style = ParagraphStyle(
        'SuperCompactTitle',
        parent=styles['Heading1'],
        fontSize=12,
        spaceAfter=8,
        spaceBefore=0,
        alignment=1  # Center alignment
    )
    
    # Super compact heading styles
    state_style = ParagraphStyle(
        'StateHeading',
        parent=styles['Heading2'],
        fontSize=10,
        spaceAfter=2,
        spaceBefore=6,
        textColor=colors.black,
        fontName='Helvetica-Bold'
    )
    
    county_style = ParagraphStyle(
        'CountyHeading',
        parent=styles['Heading3'],
        fontSize=9,
        spaceAfter=1,
        spaceBefore=4,
        leftIndent=8,
        textColor=colors.darkblue,
        fontName='Helvetica-Bold'
    )
    
    property_style = ParagraphStyle(
        'PropertyStyle',
        parent=styles['Normal'],
        fontSize=8,
        spaceAfter=1,
        spaceBefore=2,
        leftIndent=16,
        fontName='Helvetica-Bold'
    )
    
    # Super compact date style
    date_style = ParagraphStyle(
        'DateStyle',
        parent=styles['Normal'],
        fontSize=7,
        spaceAfter=4,
        alignment=1  # Center alignment
    )
    
    # Title and date
    story.append(Paragraph("Property Data Completeness Checklist", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%m/%d/%Y')}", date_style))
    
    # Required fields for reference
    required_fields = {
        'custom.All_APN': 'APN',
        'custom.All_Asset_Surveyed_Acres': 'Surveyed Acres',
        'custom.All_County': 'County',
        'custom.All_RemarkableLand_URL': 'RemarkableLand URL',
        'custom.All_State': 'State',
        'custom.Asset_Cost_Basis': 'Cost Basis',
        'custom.Asset_Date_Purchased': 'Date Purchased',
        'custom.Asset_Original_Listing_Price': 'Original Listing Price',
        'custom.Asset_Land_ID_Internal_URL': 'Land ID Internal URL',
        'custom.Asset_Land_ID_Share_URL': 'Land ID Share URL',
        'custom.Asset_MLS#': 'MLS#',
        'custom.Asset_MLS_Listing_Date': 'MLS Listing Date',
        'custom.Asset_Street_Address': 'Street Address',
        'custom.Asset_Last_Mapping_Audit': 'Last Map Audit',
        'avg_one_time_active_opportunity_value': 'Avg One Time Active Opportunity Value'
    }
    
    # Filter to only properties with missing information
    incomplete_properties = df[df['missing_information'] != '✅ Complete'].copy()
    
    if len(incomplete_properties) == 0:
        story.append(Paragraph("🎉 Congratulations! All properties have complete data.", styles['Normal']))
        doc.build(story)
        buffer.seek(0)
        return buffer
    
    # Sort by State, then County, then Property Name
    sort_columns = []
    if 'custom.All_State' in incomplete_properties.columns:
        sort_columns.append('custom.All_State')
    if 'custom.All_County' in incomplete_properties.columns:
        sort_columns.append('custom.All_County')
    if 'display_name' in incomplete_properties.columns:
        sort_columns.append('display_name')
    
    if sort_columns:
        incomplete_properties = incomplete_properties.sort_values(sort_columns)
    
    # Group by State and County for ultra-compact layout
    current_state = None
    current_county = None
    
    for _, row in incomplete_properties.iterrows():
        state = row.get('custom.All_State', 'Unknown State')
        county = row.get('custom.All_County', 'Unknown County')
        property_name = row.get('display_name', 'Unknown Property')
        missing_info = row.get('missing_information', '')
        
        # Add state header if changed (ultra compact)
        if state != current_state:
            current_state = state
            story.append(Spacer(1, 4))  # Minimal spacing
            story.append(Paragraph(f"STATE: {state}", state_style))
            current_county = None  # Reset county when state changes
        
        # Add county header if changed (ultra compact)
        if county != current_county:
            current_county = county
            story.append(Spacer(1, 2))  # Minimal spacing
            story.append(Paragraph(f"{county} County", county_style))
        
        # Property name (ultra compact)
        story.append(Spacer(1, 1))  # Minimal spacing
        # Truncate very long property names for better fit
        display_name = property_name[:60] + "..." if len(property_name) > 60 else property_name
        story.append(Paragraph(f"{display_name}", property_style))
        
        # Parse missing fields and create ultra-compact checkboxes in 3 columns
        if missing_info.startswith('❌ Missing: '):
            missing_fields_text = missing_info.replace('❌ Missing: ', '')
            missing_fields_list = [field.strip() for field in missing_fields_text.split(',')]
            
            # Create ultra-compact checklist - 3 items per row for maximum space utilization
            if missing_fields_list:
                rows = []
                for i in range(0, len(missing_fields_list), 3):
                    row = []
                    for j in range(3):
                        if i + j < len(missing_fields_list):
                            field = missing_fields_list[i + j]
                            # Truncate long field names
                            short_field = field[:18] + ('...' if len(field) > 18 else '')
                            row.append('☐ ' + short_field)
                        else:
                            row.append('')
                    rows.append(row)
                
                # Create super compact table with 3 columns
                if rows:
                    checklist_table = Table(rows, colWidths=[1.8*inch, 1.8*inch, 1.8*inch])
                    checklist_table.setStyle(TableStyle([
                        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 7),  # Very small font
                        ('LEFTPADDING', (0, 0), (-1, -1), 20),  # Indent from property name
                        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),   # No top padding
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0), # No bottom padding
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ]))
                    story.append(checklist_table)
        
        # No spacing between properties to maximize density
    
    # Build the PDF
    try:
        doc.build(story)
        buffer.seek(0)
        return buffer
    except Exception as e:
        st.error(f"Error generating PDF: {str(e)}")
        return None

def display_detailed_tables(df):
    """Display detailed property information with filtering"""
    st.header("📋 Detailed Property Information")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_filter = st.selectbox(
            "Filter by Opportunity Status",
            ["All"] + ['Purchased', 'Listed', 'Under Contract']
        )
    
    with col2:
        if 'custom.All_State' in df.columns:
            state_filter = st.selectbox(
                "Filter by State",
                ["All"] + sorted(df['custom.All_State'].unique().tolist())
            )
        else:
            state_filter = "All"
    
    with col3:
        if 'custom.All_County' in df.columns:
            county_filter = st.selectbox(
                "Filter by County",
                ["All"] + sorted(df['custom.All_County'].unique().tolist())
            )
        else:
            county_filter = "All"
    
    # Apply filters
    filtered_df = df.copy()
    if status_filter != "All":
        filtered_df = filtered_df[filtered_df['primary_opportunity_status_label'] == status_filter]
    if state_filter != "All":
        filtered_df = filtered_df[filtered_df['custom.All_State'] == state_filter]
    if county_filter != "All":
        filtered_df = filtered_df[filtered_df['custom.All_County'] == county_filter]
    
    # Apply default sort order: Status (custom order), State (alphabetical), County (alphabetical)
    if len(filtered_df) > 0:
        # Create a status order mapping for sorting
        status_order_map = {'Purchased': 1, 'Listed': 2, 'Under Contract': 3}
        
        # Add temporary sort column for status ordering
        if 'primary_opportunity_status_label' in filtered_df.columns:
            filtered_df['_status_sort'] = filtered_df['primary_opportunity_status_label'].map(status_order_map).fillna(999)
        
        # Sort by: Status (custom order), State (alphabetical), County (alphabetical)
        sort_columns = []
        if 'primary_opportunity_status_label' in filtered_df.columns:
            sort_columns.append('_status_sort')
        if 'custom.All_State' in filtered_df.columns:
            sort_columns.append('custom.All_State')
        if 'custom.All_County' in filtered_df.columns:
            sort_columns.append('custom.All_County')
        
        if sort_columns:
            filtered_df = filtered_df.sort_values(sort_columns, ascending=True)
        
        # Remove the temporary sort column
        if '_status_sort' in filtered_df.columns:
            filtered_df = filtered_df.drop('_status_sort', axis=1)
    
    st.subheader(f"Showing {len(filtered_df)} properties")
    
    # Select key columns for display - Lead Count added between Acres and Current Asking Price
    desired_columns = [
        'display_name',                         # Property Name (Left)
        'primary_opportunity_status_label',     # Status (Left)
        'custom.All_State',                     # State (Left)
        'custom.All_County',                    # County (Left)
        'custom.All_APN',                       # APN (Left)
        'custom.All_Asset_Surveyed_Acres',      # Acres (Right)
        'lead_count',                           # Lead Count (Center) - NEW POSITION
        'primary_opportunity_value',            # Current Asking Price (Right)
        'custom.Asset_Cost_Basis',              # Cost Basis (Right)
        'current_margin',                       # Profit Margin (Right)
        'current_margin_pct',                   # Margin (Center)
        'markup_percentage',                    # Markup (Center)
        'price_per_acre',                       # Asking Price/Acre (Right)
        'cost_basis_per_acre',                  # Cost Basis/Acre (Right)
        'custom.Asset_Original_Listing_Price',  # Original Listing Price (Right)
        'percent_of_initial_listing',           # %OLP (Center)
        'days_on_market',                       # DOM (Center)
        'price_reductions',                     # Price Reductions (Center)
        'custom.Asset_Last_Mapping_Audit',     # Last Mapping Audit (Center)
        'missing_information'                   # Missing Information (Left)
    ]
    
    # Force include columns
    display_columns = []
    for col in desired_columns:
        if col in filtered_df.columns:
            display_columns.append(col)
    
    if display_columns:
        # FORCE include Original Listing Price if it exists
        if 'custom.Asset_Original_Listing_Price' in filtered_df.columns and 'custom.Asset_Original_Listing_Price' not in display_columns:
            try:
                pos = display_columns.index('primary_opportunity_value')
                display_columns.insert(pos, 'custom.Asset_Original_Listing_Price')
            except ValueError:
                display_columns.append('custom.Asset_Original_Listing_Price')
        
        # FORCE include Cost Basis per Acre if it exists
        if 'cost_basis_per_acre' in filtered_df.columns and 'cost_basis_per_acre' not in display_columns:
            try:
                pos = display_columns.index('current_margin')
                display_columns.insert(pos, 'cost_basis_per_acre')
            except ValueError:
                display_columns.append('cost_basis_per_acre')
        
        display_df = filtered_df[display_columns].copy()
        
        # Format currency columns
        currency_columns = ['custom.Asset_Original_Listing_Price', 'primary_opportunity_value', 'custom.Asset_Cost_Basis', 'cost_basis_per_acre', 'current_margin', 'price_per_acre']
        for col in currency_columns:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")
        
        # Format percentage columns
        percentage_columns = ['markup_percentage', 'percent_of_initial_listing']
        for col in percentage_columns:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else "N/A")
        
        # Format margin percentage separately with no decimals
        if 'current_margin_pct' in display_df.columns:
            display_df['current_margin_pct'] = display_df['current_margin_pct'].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else "N/A")
        
        # Format numeric columns (including rounded DOM)
        if 'custom.All_Asset_Surveyed_Acres' in display_df.columns:
            display_df['custom.All_Asset_Surveyed_Acres'] = display_df['custom.All_Asset_Surveyed_Acres'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        
        # Format DOM with no decimals (rounded to whole days)
        if 'days_on_market' in display_df.columns:
            display_df['days_on_market'] = display_df['days_on_market'].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "N/A")
        
        # Format price reductions with dash for none, lowercase x for reductions
        if 'price_reductions' in display_df.columns:
            display_df['price_reductions'] = display_df['price_reductions'].apply(
                lambda x: "-" if pd.notna(x) and x == 0 else f"{x:.0f}x" if pd.notna(x) else "N/A"
            )
        
        # Format Last Mapping Audit date with 60-day warning
        if 'custom.Asset_Last_Mapping_Audit' in display_df.columns:
            def format_audit_date(date_val):
                if pd.isna(date_val) or date_val == '':
                    return "N/A"
                try:
                    # Try to parse the date and format it nicely
                    parsed_date = pd.to_datetime(date_val)
                    formatted_date = parsed_date.strftime('%m/%d/%Y')
                    
                    # Check if more than 60 days old
                    days_old = (datetime.now() - parsed_date).days
                    if days_old > 60:
                        return f"🔴 {formatted_date}"
                    else:
                        return formatted_date
                except:
                    return str(date_val)  # Return as-is if parsing fails
            
            display_df['custom.Asset_Last_Mapping_Audit'] = display_df['custom.Asset_Last_Mapping_Audit'].apply(format_audit_date)
        
        # Color-code the Status column with emojis (Streamlit dataframes don't support HTML)
        if 'primary_opportunity_status_label' in display_df.columns:
            def format_status(status):
                if status == 'Purchased':
                    return f'🔴 {status}'     # Red circle
                elif status == 'Listed':
                    return f'🔵 {status}'     # Blue circle
                elif status == 'Under Contract':
                    return f'🟢 {status}'     # Green circle
                else:
                    return status
            
            display_df['primary_opportunity_status_label'] = display_df['primary_opportunity_status_label'].apply(format_status)
        
        # Rename columns for display with updated headers
        display_df = display_df.rename(columns={
            'display_name': 'Property Name',
            'primary_opportunity_status_label': 'Status',
            'custom.All_State': 'State',
            'custom.All_County': 'County',
            'custom.All_APN': 'APN',
            'custom.All_Asset_Surveyed_Acres': 'Acres',
            'lead_count': 'Lead Count',
            'primary_opportunity_value': 'Current Asking Price',
            'custom.Asset_Cost_Basis': 'Cost Basis',
            'current_margin': 'Profit Margin',
            'current_margin_pct': 'Margin',
            'markup_percentage': 'Markup',
            'price_per_acre': 'Asking Price/Acre',
            'cost_basis_per_acre': 'Cost Basis/Acre',
            'custom.Asset_Original_Listing_Price': 'Original Listing Price',
            'percent_of_initial_listing': '%OLP',
            'days_on_market': 'DOM',
            'price_reductions': 'Price Reductions',
            'custom.Asset_Last_Mapping_Audit': 'Last Map Audit',
            'missing_information': 'Missing Information'
        })
        
        # Display table with custom CSS for column alignment
        st.markdown("""
        <style>
        .dataframe th:nth-child(1), .dataframe td:nth-child(1) { text-align: left !important; }    /* Property Name */
        .dataframe th:nth-child(2), .dataframe td:nth-child(2) { text-align: left !important; }    /* Status */
        .dataframe th:nth-child(3), .dataframe td:nth-child(3) { text-align: left !important; }    /* State */
        .dataframe th:nth-child(4), .dataframe td:nth-child(4) { text-align: left !important; }    /* County */
        .dataframe th:nth-child(5), .dataframe td:nth-child(5) { text-align: left !important; }    /* APN */
        .dataframe th:nth-child(6), .dataframe td:nth-child(6) { text-align: right !important; }   /* Acres */
        .dataframe th:nth-child(7), .dataframe td:nth-child(7) { text-align: center !important; }  /* Lead Count */
        .dataframe th:nth-child(8), .dataframe td:nth-child(8) { text-align: right !important; }   /* Current Asking Price */
        .dataframe th:nth-child(9), .dataframe td:nth-child(9) { text-align: right !important; }   /* Cost Basis */
        .dataframe th:nth-child(10), .dataframe td:nth-child(10) { text-align: right !important; }  /* Profit Margin */
        .dataframe th:nth-child(11), .dataframe td:nth-child(11) { text-align: center !important; } /* Margin */
        .dataframe th:nth-child(12), .dataframe td:nth-child(12) { text-align: center !important; } /* Markup */
        .dataframe th:nth-child(13), .dataframe td:nth-child(13) { text-align: right !important; }  /* Asking Price/Acre */
        .dataframe th:nth-child(14), .dataframe td:nth-child(14) { text-align: right !important; }  /* Cost Basis/Acre */
        .dataframe th:nth-child(15), .dataframe td:nth-child(15) { text-align: right !important; }  /* Original Listing Price */
        .dataframe th:nth-child(16), .dataframe td:nth-child(16) { text-align: center !important; } /* %OLP */
        .dataframe th:nth-child(17), .dataframe td:nth-child(17) { text-align: center !important; } /* DOM */
        .dataframe th:nth-child(18), .dataframe td:nth-child(18) { text-align: center !important; } /* Price Reductions */
        .dataframe th:nth-child(19), .dataframe td:nth-child(19) { text-align: center !important; } /* Last Map Audit */
        .dataframe th:nth-child(20), .dataframe td:nth-child(20) { text-align: left !important; }   /* Missing Information */
        </style>
        """, unsafe_allow_html=True)
        
        st.dataframe(display_df, use_container_width=True)
        
        # Add summary of missing information
        if 'missing_information' in filtered_df.columns:
            st.subheader("📊 Data Completeness Summary")
            complete_count = len(filtered_df[filtered_df['missing_information'] == '✅ Complete'])
            incomplete_count = len(filtered_df) - complete_count
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Complete Properties", f"{complete_count}/{len(filtered_df)}")
            with col2:
                completion_rate = (complete_count / len(filtered_df)) * 100 if len(filtered_df) > 0 else 0
                st.metric("Completion Rate", f"{completion_rate:.1f}%")
            with col3:
                st.metric("Incomplete Properties", incomplete_count)
                
            # Show most common missing fields
            if incomplete_count > 0:
                st.write("**Most Common Missing Fields:**")
                incomplete_props = filtered_df[filtered_df['missing_information'] != '✅ Complete']
                missing_fields_list = []
                for missing_info in incomplete_props['missing_information']:
                    if missing_info.startswith('❌ Missing: '):
                        fields = missing_info.replace('❌ Missing: ', '').split(', ')
                        missing_fields_list.extend(fields)
                
                if missing_fields_list:
                    from collections import Counter
                    field_counts = Counter(missing_fields_list)
                    missing_summary = []
                    for field, count in field_counts.most_common():
                        percentage = (count / len(filtered_df)) * 100
                        missing_summary.append({
                            'Missing Field': field,
                            'Properties Missing': count,
                            'Percentage': f"{percentage:.1f}%"
                        })
                    
                    st.dataframe(pd.DataFrame(missing_summary), use_container_width=True)
        
        # Add PDF download button for missing fields checklist
        st.subheader("📄 Download Missing Fields Checklist")
        if st.button("Generate PDF Checklist", type="primary"):
            pdf_buffer = generate_missing_fields_checklist_pdf(filtered_df)
            if pdf_buffer:
                st.download_button(
                    label="📥 Download PDF Checklist",
                    data=pdf_buffer,
                    file_name=f"missing_fields_checklist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf"
                )

def main():
    st.title("🏞️ Land Portfolio Analyzer")
    st.markdown("### Hierarchical Analysis: Opportunity Status → State → County")
    st.markdown("**Status Order**: Purchased → Listed → Under Contract")
    
    uploaded_file = st.file_uploader("Upload your CRM CSV export", type=['csv'])
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.success(f"✅ Loaded {len(df)} properties successfully!")
            
            # Process the data
            processed_df = process_data(df)
            
            # Main hierarchy analysis
            display_hierarchy_breakdown(processed_df)
            
            st.divider()
            
            # Visualizations
            create_visualizations(processed_df)
            
            st.divider()
            
            # Detailed tables with filtering
            display_detailed_tables(processed_df)
            
            # Raw data preview
            with st.expander("🔍 Raw Data Preview"):
                st.dataframe(processed_df.head(10), use_container_width=True)
                
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
            st.write("Please check that your CSV file contains the expected columns.")
    else:
        st.info("👆 Upload your CSV file to begin analysis")
        
        st.markdown("""
        ### Required Fields for Complete Data
        - **APN** (custom.All_APN)
        - **Surveyed Acres** (custom.All_Asset_Surveyed_Acres)
        - **County** (custom.All_County)
        - **RemarkableLand URL** (custom.All_RemarkableLand_URL)
        - **State** (custom.All_State)
        - **Cost Basis** (custom.Asset_Cost_Basis)
        - **Date Purchased** (custom.Asset_Date_Purchased)
        - **Original Listing Price** (custom.Asset_Original_Listing_Price)
        - **Land ID Internal URL** (custom.Asset_Land_ID_Internal_URL)
        - **Land ID Share URL** (custom.Asset_Land_ID_Share_URL)
        - **MLS#** (custom.Asset_MLS#)
        - **MLS Listing Date** (custom.Asset_MLS_Listing_Date)
        - **Last Map Audit** (custom.Asset_Last_Mapping_Audit)
        - **Street Address** (custom.Asset_Street_Address)
        - **Avg One Time Active Opportunity Value** (avg_one_time_active_opportunity_value)
        
        **Note**: To use PDF generation, install reportlab: `pip install reportlab`
        
        ### Price Reduction System
        Automatically calculated from trailing digit of current value:
        - **9**: No reductions | **8**: 1 reduction | **7**: 2 reductions
        - **6**: 3 reductions | **5**: 4 reductions | **4**: 5 reductions
        - And so on...
        """)

if __name__ == "__main__":
    main()

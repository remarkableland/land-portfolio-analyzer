Step 2: Create the Main Application File
We'll create the app.py file directly in GitHub.

In your GitHub repository:

Click the "Add file" button → "Create new file"
Name the file: Type app.py in the filename field
Copy and paste the following code into the file editor:
python
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import io

# Page configuration
st.set_page_config(
    page_title="Land Portfolio Analyzer",
    page_icon="🏞️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Field mappings for CRM data
FIELD_MAPPINGS = {
    'property_id': 'id',
    'property_name': 'display_name', 
    'opportunity_status': 'primary_opportunity_status_label',
    'state': 'custom.All_State',
    'county': 'custom.All_County',
    'address': 'custom.Asset_Street_Address',
    'cost_basis': 'custom.Asset_Cost_Basis',
    'initial_price': 'custom.Asset_Initial_Listing_Price',
    'current_value': 'primary_opportunity_value',
    'min_price': 'custom.Asset_Minimum_Price',
    'acres': 'custom.All_Asset_Surveyed_Acres',
    'purchase_date': 'custom.Asset_Date_Purchased',
    'listing_date': 'custom.Asset_MLS_Listing_Date',
    'sale_date': 'custom.Asset_Date_Sold',
    'opportunity_created': 'primary_opportunity_created',
    'gross_sales_price': 'custom.Asset_Gross_Sales_Price'
}

def count_price_reductions(price):
    """Count price reductions based on trailing digit"""
    if pd.isna(price) or price == 0:
        return 0
    
    trailing_digit = int(str(int(price))[-1])
    
    if trailing_digit == 9:
        return 0  # No reductions
    elif trailing_digit == 8:
        return 1
    elif trailing_digit == 7:
        return 2
    elif trailing_digit == 6:
        return 3
    elif trailing_digit == 5:
        return 4
    elif trailing_digit == 4:
        return 5
    elif trailing_digit == 3:
        return 6
    elif trailing_digit == 2:
        return 7
    elif trailing_digit == 1:
        return 8
    elif trailing_digit == 0:
        return 9
    else:
        return 0

def calculate_days_on_market(row):
    """Calculate days on market from MLS listing date"""
    listing_date = row.get('custom.Asset_MLS_Listing_Date')
    sale_date = row.get('custom.Asset_Date_Sold')
    
    if pd.isna(listing_date):
        return None
    
    try:
        if isinstance(listing_date, str):
            listing_dt = pd.to_datetime(listing_date)
        else:
            listing_dt = listing_date
            
        if not pd.isna(sale_date):
            # Property was sold
            if isinstance(sale_date, str):
                sale_dt = pd.to_datetime(sale_date)
            else:
                sale_dt = sale_date
            return (sale_dt - listing_dt).days
        else:
            # Property still active
            return (datetime.now() - listing_dt).days
    except:
        return None

def process_data(df):
    """Process and clean the uploaded data"""
    # Create a copy to avoid modifying original
    processed_df = df.copy()
    
    # Clean county names (standardize case)
    processed_df['custom.All_County'] = processed_df['custom.All_County'].str.title()
    
    # Handle null counties
    processed_df['custom.All_County'] = processed_df['custom.All_County'].fillna('Unknown County')
    
    # Calculate derived metrics
    processed_df['price_reductions'] = processed_df['primary_opportunity_value'].apply(count_price_reductions)
    processed_df['days_on_market'] = processed_df.apply(calculate_days_on_market, axis=1)
    
    # Calculate margins
    processed_df['current_margin'] = processed_df['primary_opportunity_value'] - processed_df['custom.Asset_Cost_Basis']
    processed_df['current_margin_pct'] = ((processed_df['primary_opportunity_value'] - processed_df['custom.Asset_Cost_Basis']) / 
                                         processed_df['custom.Asset_Cost_Basis'] * 100)
    
    # Calculate price per acre
    processed_df['price_per_acre'] = processed_df['primary_opportunity_value'] / processed_df['custom.All_Asset_Surveyed_Acres']
    processed_df['cost_per_acre'] = processed_df['custom.Asset_Cost_Basis'] / processed_df['custom.All_Asset_Surveyed_Acres']
    
    return processed_df

def display_hierarchy_view(df):
    """Display hierarchical breakdown with expandable sections"""
    st.header("📊 Portfolio Hierarchy Breakdown")
    
    # Overall portfolio metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Properties", len(df))
    with col2:
        st.metric("Total Portfolio Value", f"${df['primary_opportunity_value'].sum():,.0f}")
    with col3:
        st.metric("Total Cost Basis", f"${df['custom.Asset_Cost_Basis'].sum():,.0f}")
    with col4:
        total_margin = df['current_margin'].sum()
        st.metric("Total Portfolio Margin", f"${total_margin:,.0f}")
    
    st.divider()
    
    # Level 1: Opportunity Status breakdown
    st.subheader("🎯 By Opportunity Status")
    
    status_data = []
    for status in df['primary_opportunity_status_label'].unique():
        if pd.notna(status):
            status_df = df[df['primary_opportunity_status_label'] == status]
            status_data.append({
                'Status': status,
                'Properties': len(status_df),
                'Total Value': f"${status_df['primary_opportunity_value'].sum():,.0f}",
                'Avg DOM': f"{status_df['days_on_market'].mean():.0f}" if status_df['days_on_market'].notna().any() else "N/A",
                'Avg Reductions': f"{status_df['price_reductions'].mean():.1f}",
                'Total Margin': f"${status_df['current_margin'].sum():,.0f}"
            })
    
    status_overview_df = pd.DataFrame(status_data)
    st.dataframe(status_overview_df, use_container_width=True)
    
    # Expandable sections for each status
    for status in df['primary_opportunity_status_label'].unique():
        if pd.notna(status):
            with st.expander(f"📋 {status} - Detailed Breakdown"):
                status_df = df[df['primary_opportunity_status_label'] == status]
                
                st.subheader(f"States within {status}")
                
                # State level breakdown
                state_data = []
                for state in status_df['custom.All_State'].unique():
                    if pd.notna(state):
                        state_df = status_df[status_df['custom.All_State'] == state]
                        state_data.append({
                            'State': state,
                            'Properties': len(state_df),
                            'Total Value': f"${state_df['primary_opportunity_value'].sum():,.0f}",
                            'Avg DOM': f"{state_df['days_on_market'].mean():.0f}" if state_df['days_on_market'].notna().any() else "N/A",
                            'Total Acres': f"{state_df['custom.All_Asset_Surveyed_Acres'].sum():.0f}",
                            'Avg Price/Acre': f"${state_df['price_per_acre'].mean():,.0f}" if state_df['price_per_acre'].notna().any() else "N/A"
                        })
                
                if state_data:
                    state_breakdown_df = pd.DataFrame(state_data)
                    st.dataframe(state_breakdown_df, use_container_width=True)
                
                # County level breakdown for each state
                for state in status_df['custom.All_State'].unique():
                    if pd.notna(state):
                        state_df = status_df[status_df['custom.All_State'] == state]
                        
                        st.write(f"**{state} Counties:**")
                        
                        county_data = []
                        for county in state_df['custom.All_County'].unique():
                            if pd.notna(county):
                                county_df = state_df[state_df['custom.All_County'] == county]
                                county_data.append({
                                    'County': county,
                                    'Properties': len(county_df),
                                    'Total Value': f"${county_df['primary_opportunity_value'].sum():,.0f}",
                                    'Avg DOM': f"{county_df['days_on_market'].mean():.0f}" if county_df['days_on_market'].notna().any() else "N/A",
                                    'Total Acres': f"{county_df['custom.All_Asset_Surveyed_Acres'].sum():.1f}",
                                    'Avg Margin %': f"{county_df['current_margin_pct'].mean():.1f}%" if county_df['current_margin_pct'].notna().any() else "N/A"
                                })
                        
                        if county_data:
                            county_breakdown_df = pd.DataFrame(county_data)
                            st.dataframe(county_breakdown_df, use_container_width=True)

def create_visualizations(df):
    """Create visualizations for the dashboard"""
    st.header("📈 Portfolio Visualizations")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Opportunity Status Distribution
        st.subheader("Properties by Opportunity Status")
        status_counts = df['primary_opportunity_status_label'].value_counts()
        fig_pie = px.pie(values=status_counts.values, names=status_counts.index, 
                        title="Portfolio Distribution by Status")
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        # State Distribution
        st.subheader("Properties by State")
        state_counts = df['custom.All_State'].value_counts()
        fig_bar = px.bar(x=state_counts.index, y=state_counts.values,
                        title="Portfolio Distribution by State",
                        labels={'x': 'State', 'y': 'Number of Properties'})
        st.plotly_chart(fig_bar, use_container_width=True)

def main():
    st.title("🏞️ Land Portfolio Analyzer")
    st.markdown("### Hierarchical Analysis: Opportunity Status → State → County")
    
    # Sidebar
    st.sidebar.header("📁 Data Upload")
    
    uploaded_file = st.sidebar.file_uploader(
        "Upload your CRM CSV export",
        type=['csv'],
        help="Upload the CSV file exported from your CRM system"
    )
    
    if uploaded_file is not None:
        try:
            # Load and preview data
            df = pd.read_csv(uploaded_file)
            
            st.sidebar.success(f"✅ File loaded successfully!")
            st.sidebar.info(f"📊 {len(df)} properties found")
            
            # Data preview section
            with st.expander("🔍 Data Preview", expanded=False):
                st.subheader("Raw Data Sample")
                st.dataframe(df.head(), use_container_width=True)
                
                st.subheader("Key Fields Check")
                key_fields = list(FIELD_MAPPINGS.values())
                available_fields = [field for field in key_fields if field in df.columns]
                missing_fields = [field for field in key_fields if field not in df.columns]
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("✅ **Available Fields:**")
                    for field in available_fields:
                        st.write(f"- {field}")
                
                with col2:
                    if missing_fields:
                        st.write("❌ **Missing Fields:**")
                        for field in missing_fields:
                            st.write(f"- {field}")
            
            # Process the data
            processed_df = process_data(df)
            
            # Display the main dashboard
            display_hierarchy_view(processed_df)
            
            st.divider()
            
            # Visualizations
            create_visualizations(processed_df)
            
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
            st.info("Please ensure your CSV file is in the correct format.")
    
    else:
        st.info("👆 Please upload a CSV file to begin analysis")
        
        st.markdown("""
        ### Expected CSV Format
        Your CSV should contain the following key fields from your CRM export:
        
        - `id` - Property identifier
        - `primary_opportunity_status_label` - Status (Listed, Under Contract, Purchased)
        - `custom.All_State` - State location
        - `custom.All_County` - County location
        - `custom.Asset_Cost_Basis` - Original cost
        - `primary_opportunity_value` - Current listing value
        - `custom.All_Asset_Surveyed_Acres` - Property size
        - `custom.Asset_MLS_Listing_Date` - MLS listing date
        
        ### Price Reduction Tracking
        Price reductions are automatically calculated based on the trailing digit:
        - Ends in 9: No reductions  
        - Ends in 8: 1 reduction
        - Ends in 7: 2 reductions
        - And so on...
        """)

if __name__ == "__main__":
    main()






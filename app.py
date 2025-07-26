import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

st.set_page_config(
    page_title="Land Portfolio Analyzer",
    page_icon="🏞️",
    layout="wide"
)

def count_price_reductions(price):
    """Count price reductions based on trailing digit"""
    if pd.isna(price) or price == 0:
        return 0
    
    trailing_digit = int(str(int(price))[-1])
    reduction_map = {9: 0, 8: 1, 7: 2, 6: 3, 5: 4, 4: 5, 3: 6, 2: 7, 1: 8, 0: 9}
    return reduction_map.get(trailing_digit, 0)

def calculate_days_on_market(row):
    """Calculate days on market from MLS listing date"""
    listing_date = row.get('custom.Asset_MLS_Listing_Date')
    if pd.isna(listing_date):
        return None
    
    try:
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
    processed_df = df.copy()
    
    # Clean and standardize data
    if 'custom.All_County' in processed_df.columns:
        processed_df['custom.All_County'] = processed_df['custom.All_County'].fillna('Unknown County')
        processed_df['custom.All_County'] = processed_df['custom.All_County'].astype(str).str.title()
    
    # Calculate metrics
    if 'primary_opportunity_value' in processed_df.columns:
        processed_df['price_reductions'] = processed_df['primary_opportunity_value'].apply(count_price_reductions)
    
    processed_df['days_on_market'] = processed_df.apply(calculate_days_on_market, axis=1)
    
    # Financial calculations
    if all(col in processed_df.columns for col in ['primary_opportunity_value', 'custom.Asset_Cost_Basis']):
        processed_df['current_margin'] = processed_df['primary_opportunity_value'] - processed_df['custom.Asset_Cost_Basis']
        processed_df['current_margin_pct'] = (processed_df['current_margin'] / processed_df['custom.Asset_Cost_Basis'] * 100)
    
    # Price per acre
    if all(col in processed_df.columns for col in ['primary_opportunity_value', 'custom.All_Asset_Surveyed_Acres']):
        processed_df['price_per_acre'] = processed_df['primary_opportunity_value'] / processed_df['custom.All_Asset_Surveyed_Acres']
    
    # Calculate markup percentage (Current Asking Price minus Cost Basis divided by Cost Basis)
    if all(col in processed_df.columns for col in ['primary_opportunity_value', 'custom.Asset_Cost_Basis']):
        processed_df['markup_percentage'] = ((processed_df['primary_opportunity_value'] - processed_df['custom.Asset_Cost_Basis']) / 
                                           processed_df['custom.Asset_Cost_Basis'] * 100)
    
    # Calculate cost basis per acre
    if all(col in processed_df.columns for col in ['custom.Asset_Cost_Basis', 'custom.All_Asset_Surveyed_Acres']):
        processed_df['cost_basis_per_acre'] = processed_df['custom.Asset_Cost_Basis'] / processed_df['custom.All_Asset_Surveyed_Acres']
    
    # Calculate percent of original listing price
    if all(col in processed_df.columns for col in ['primary_opportunity_value', 'custom.Asset_Original_Listing_Price']):
        processed_df['percent_of_initial_listing'] = (processed_df['primary_opportunity_value'] / 
                                                     processed_df['custom.Asset_Original_Listing_Price'] * 100)
    
    # Check missing information for each property
    processed_df['missing_information'] = processed_df.apply(check_missing_information, axis=1)
    
    return processed_df

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
                    'Avg Reductions': f"{status_df['price_reductions'].mean():.1f}" if 'price_reductions' in status_df.columns else 'N/A'
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
    
    # Select key columns for display - NEW ORDER with APN added
    desired_columns = [
        'display_name',                         # Property Name (Left)
        'primary_opportunity_status_label',     # Status (Left)
        'custom.All_State',                     # State (Left)
        'custom.All_County',                    # County (Left)
        'custom.All_APN',                       # APN (Left)
        'custom.All_Asset_Surveyed_Acres',      # Acres (Right)
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
        
        # Color-code the Status column with your preferred emojis
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
            'missing_information': 'Missing Information'
        })
        
        # Display table with custom CSS for column alignment
        st.markdown("""
        <style>
        .dataframe th:nth-child(1), .dataframe td:nth-child(1) { text-align: left !important; }    /* Property Name */
        .dataframe th:nth-child(2), .dataframe td:nth-child(2) { text-align: left !important; }    /* Status */
        .dataframe th:nth-child(3), .dataframe td:nth-child(3) { text-align: left !important; }    /* State */
        .dataframe th:nth-child(4), .dataframe td:nth-child(4) { text-align: left !important; }    /* County */
        .dataframe th:nth-child(5), .dataframe td:nth-child(5) { text-align: right !important; }   /* Acres */
        .dataframe th:nth-child(6), .dataframe td:nth-child(6) { text-align: right !important; }   /* Current Asking Price */
        .dataframe th:nth-child(7), .dataframe td:nth-child(7) { text-align: right !important; }   /* Cost Basis */
        .dataframe th:nth-child(8), .dataframe td:nth-child(8) { text-align: right !important; }   /* Profit Margin */
        .dataframe th:nth-child(9), .dataframe td:nth-child(9) { text-align: center !important; }  /* Margin */
        .dataframe th:nth-child(10), .dataframe td:nth-child(10) { text-align: center !important; } /* Markup */
        .dataframe th:nth-child(11), .dataframe td:nth-child(11) { text-align: right !important; }  /* Asking Price/Acre */
        .dataframe th:nth-child(12), .dataframe td:nth-child(12) { text-align: right !important; }  /* Cost Basis/Acre */
        .dataframe th:nth-child(13), .dataframe td:nth-child(13) { text-align: right !important; }  /* Original Listing Price */
        .dataframe th:nth-child(14), .dataframe td:nth-child(14) { text-align: center !important; } /* %OLP */
        .dataframe th:nth-child(15), .dataframe td:nth-child(15) { text-align: center !important; } /* DOM */
        .dataframe th:nth-child(16), .dataframe td:nth-child(16) { text-align: center !important; } /* Price Reductions */
        .dataframe th:nth-child(17), .dataframe td:nth-child(17) { text-align: left !important; }   /* Missing Information */
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
        - **Street Address** (custom.Asset_Street_Address)
        - **Avg One Time Active Opportunity Value** (avg_one_time_active_opportunity_value)
        
        ### Price Reduction System
        Automatically calculated from trailing digit of current value:
        - **9**: No reductions | **8**: 1 reduction | **7**: 2 reductions
        - **6**: 3 reductions | **5**: 4 reductions | **4**: 5 reductions
        - And so on...
        """)

if __name__ == "__main__":
    main()

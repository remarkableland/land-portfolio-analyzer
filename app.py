import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
from io import BytesIO
try:
    from reportlab.lib.pagesizes import letter, A4, A3, landscape, legal
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
        'custom.Asset_Owner': 'Owner',
        'custom.Asset_Listing_Type': 'Listing Type',
        'avg_one_time_active_opportunity_value': 'Avg One Time Active Opportunity Value'
    }
    
    missing_fields = []
    
    for field_key, field_name in required_fields.items():
        if field_key in row.index:
            value = row[field_key]
            # Special handling for Cost Basis - treat 0 as missing
            if field_key == 'custom.Asset_Cost_Basis':
                if pd.isna(value) or value == '' or value == 0:
                    missing_fields.append(field_name)
            else:
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

def wrap_text_smart(text, max_length=30):
    """Smart text wrapping that preserves readability for legal size"""
    if pd.isna(text) or text == '':
        return 'N/A'
    
    text_str = str(text)
    if len(text_str) <= max_length:
        return text_str
    
    # For property names, try to break at natural points
    words = text_str.split()
    lines = []
    current_line = ""
    
    for word in words:
        test_line = current_line + (" " + word if current_line else word)
        if len(test_line) <= max_length:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return "<br/>".join(lines)

def generate_inventory_report_pdf(df):
    """Generate a comprehensive PDF inventory report with legal size and narrow margins"""
    if not REPORTLAB_AVAILABLE:
        st.error("PDF generation requires reportlab. Please install it: pip install reportlab")
        return None
    
    # Create a BytesIO buffer for the PDF
    buffer = BytesIO()
    
    # Use legal landscape for good width (14" x 8.5" landscape)
    page_size = landscape(legal)
    
    # Create the PDF document with very narrow margins to maximize table width
    doc = SimpleDocTemplate(buffer, pagesize=page_size, 
                          topMargin=0.15*inch, bottomMargin=0.15*inch,
                          leftMargin=0.15*inch, rightMargin=0.15*inch)
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Enhanced styles for better readability
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Title'],
        fontSize=16,
        fontName='Helvetica-Bold',
        textColor=colors.darkblue,
        spaceAfter=12,
        alignment=1  # Center alignment
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica',
        spaceAfter=18,
        alignment=1  # Center alignment
    )
    
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        fontName='Helvetica-Bold',
        textColor=colors.darkblue,
        spaceAfter=8,
        spaceBefore=16
    )
    
    # Disclaimer style
    disclaimer_style = ParagraphStyle(
        'DisclaimerStyle',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica-Oblique',
        textColor=colors.grey,
        spaceAfter=8,
        spaceBefore=16,
        alignment=1,  # Center alignment
        leftIndent=20,
        rightIndent=20
    )
    
    # Title and date
    story.append(Paragraph("Remarkable Land LLC - Inventory Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))
    
    # Define the sections based on status and listing type
    primary_sections = [
        ("Purchased (Primary)", 'Purchased', 'Primary'),
        ("Listed (Primary)", 'Listed', 'Primary'), 
        ("Under Contract (Primary)", 'Under Contract', 'Primary')
    ]
    
    secondary_sections = [
        ("Listed (Secondary)", 'Listed', 'Secondary')
    ]
    
    # Process primary sections first
    primary_data_for_summary = df[
        (df['primary_opportunity_status_label'].isin(['Purchased', 'Listed', 'Under Contract'])) & 
        (df['custom.Asset_Listing_Type'] == 'Primary')
    ].copy()
    
    for section_name, status, listing_type in primary_sections:
        # Filter data for this section
        section_df = df[
            (df['primary_opportunity_status_label'] == status) & 
            (df['custom.Asset_Listing_Type'] == listing_type)
        ].copy()
        
        if len(section_df) == 0:
            continue  # Skip empty sections
        
        # Section header
        story.append(Paragraph(section_name, section_style))
        
        # Prepare table data
        table_data = []
        
        # Improved headers with better spacing
        headers = [
            'Property Name', 'Owner', 'State', 'County', 'Acres', 
            'Date Purchased', 'Cost Basis', 'Current Price', 
            'Profit Margin', 'Margin %', 'Markup %', 
            'Price/Acre', 'Cost/Acre', 'Original Price', 
            '%OLP', 'DOM'
        ]
        table_data.append(headers)
        
        # Sort by state, then county, then property name
        section_df = section_df.sort_values(['custom.All_State', 'custom.All_County', 'display_name'])
        
        for _, row in section_df.iterrows():
            # Property name with smart wrapping
            property_name = wrap_text_smart(row.get('display_name', 'Unknown Property'), 25)
            owner = wrap_text_smart(row.get('custom.Asset_Owner', 'N/A'), 15)
            state = str(row.get('custom.All_State', 'N/A'))
            county = wrap_text_smart(row.get('custom.All_County', 'N/A'), 15)
            acres = f"{row.get('custom.All_Asset_Surveyed_Acres', 0):.1f}" if pd.notna(row.get('custom.All_Asset_Surveyed_Acres')) else 'N/A'
            
            # Format date purchased
            date_purchased = 'N/A'
            if pd.notna(row.get('custom.Asset_Date_Purchased')):
                try:
                    date_val = pd.to_datetime(row.get('custom.Asset_Date_Purchased'))
                    date_purchased = date_val.strftime('%m/%d/%Y')
                except:
                    date_purchased = str(row.get('custom.Asset_Date_Purchased'))
            
            # Format financial data
            cost_basis = f"${row.get('custom.Asset_Cost_Basis', 0):,.0f}" if pd.notna(row.get('custom.Asset_Cost_Basis')) and row.get('custom.Asset_Cost_Basis', 0) > 0 else 'N/A'
            asking_price = f"${row.get('primary_opportunity_value', 0):,.0f}" if pd.notna(row.get('primary_opportunity_value')) and row.get('primary_opportunity_value', 0) > 0 else 'N/A'
            profit_margin = f"${row.get('current_margin', 0):,.0f}" if pd.notna(row.get('current_margin')) else 'N/A'
            margin_pct = f"{row.get('current_margin_pct', 0):.0f}%" if pd.notna(row.get('current_margin_pct')) else 'N/A'
            markup = f"{row.get('markup_percentage', 0):.0f}%" if pd.notna(row.get('markup_percentage')) else 'N/A'
            price_per_acre = f"${row.get('price_per_acre', 0):,.0f}" if pd.notna(row.get('price_per_acre')) and row.get('price_per_acre', 0) > 0 else 'N/A'
            cost_per_acre = f"${row.get('cost_basis_per_acre', 0):,.0f}" if pd.notna(row.get('cost_basis_per_acre')) and row.get('cost_basis_per_acre', 0) > 0 else 'N/A'
            original_price = f"${row.get('custom.Asset_Original_Listing_Price', 0):,.0f}" if pd.notna(row.get('custom.Asset_Original_Listing_Price')) and row.get('custom.Asset_Original_Listing_Price', 0) > 0 else 'N/A'
            percent_olp = f"{row.get('percent_of_initial_listing', 0):.0f}%" if pd.notna(row.get('percent_of_initial_listing')) else 'N/A'
            dom = f"{row.get('days_on_market', 0):.0f}" if pd.notna(row.get('days_on_market')) else 'N/A'
            
            # Create table row with Paragraph objects for proper text wrapping
            table_data.append([
                Paragraph(property_name, styles['Normal']),
                Paragraph(owner, styles['Normal']),
                Paragraph(state, styles['Normal']),
                Paragraph(county, styles['Normal']),
                Paragraph(acres, styles['Normal']),
                Paragraph(date_purchased, styles['Normal']),
                Paragraph(cost_basis, styles['Normal']),
                Paragraph(asking_price, styles['Normal']),
                Paragraph(profit_margin, styles['Normal']),
                Paragraph(margin_pct, styles['Normal']),
                Paragraph(markup, styles['Normal']),
                Paragraph(price_per_acre, styles['Normal']),
                Paragraph(cost_per_acre, styles['Normal']),
                Paragraph(original_price, styles['Normal']),
                Paragraph(percent_olp, styles['Normal']),
                Paragraph(dom, styles['Normal'])
            ])
        
        if len(table_data) > 1:  # Only create table if there's data beyond headers
            # Optimized column widths for legal landscape (~13.7 inches available with narrow margins)
            col_widths = [
                1.5*inch,  # Property Name
                0.9*inch,  # Owner
                0.5*inch,  # State
                0.9*inch,  # County
                0.6*inch,  # Acres
                0.9*inch,  # Date Purchased
                0.9*inch,  # Cost Basis
                1.0*inch,  # Current Price
                0.9*inch,  # Profit Margin
                0.6*inch,  # Margin %
                0.6*inch,  # Markup %
                0.9*inch,  # Price/Acre
                0.9*inch,  # Cost/Acre
                1.0*inch,  # Original Price
                0.6*inch,  # %OLP
                0.5*inch   # DOM
            ]
            
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            # Enhanced table styling with column-specific alignment
            table.setStyle(TableStyle([
                # Header row styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                
                # Data rows styling
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                
                # Column-specific alignment for data rows
                ('ALIGN', (0, 1), (1, -1), 'LEFT'),     # Property Name and Owner - LEFT
                ('ALIGN', (2, 1), (3, -1), 'CENTER'),   # State and County - CENTER
                ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),   # All remaining columns - RIGHT
                
                ('VALIGN', (0, 1), (-1, -1), 'TOP'),   # Top align for wrapped text
                
                # Grid lines
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                
                # Alternating row colors for better readability
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                
                # Better padding for readability
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            
            story.append(table)
            story.append(Spacer(1, 20))
        
        # Enhanced section summary
        section_count = len(section_df)
        total_asking = section_df['primary_opportunity_value'].sum()
        total_cost = section_df['custom.Asset_Cost_Basis'].sum()
        total_margin = total_asking - total_cost
        margin_pct = (total_margin / total_asking * 100) if total_asking > 0 else 0
        
        summary_data = [
            ['Properties', f'{section_count}', 'Total Asking Price', f'${total_asking:,.0f}'],
            ['Total Margin', f'${total_margin:,.0f}', 'Total Cost Basis', f'${total_cost:,.0f}'],
            ['Portfolio Margin %', f'{margin_pct:.1f}%', '', '']
        ]
        
        summary_table = Table(summary_data, colWidths=[1.8*inch, 1.5*inch, 1.8*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 28))
    
    # Enhanced primary portfolio summary (only primary sections)
    story.append(Paragraph("Primary Portfolio Summary", section_style))
    
    total_properties_primary = len(primary_data_for_summary)
    total_asking_primary = primary_data_for_summary['primary_opportunity_value'].sum()
    total_cost_primary = primary_data_for_summary['custom.Asset_Cost_Basis'].sum()
    total_margin_primary = total_asking_primary - total_cost_primary
    overall_margin_pct_primary = (total_margin_primary / total_asking_primary * 100) if total_asking_primary > 0 else 0
    
    primary_summary_data = [
        ['Total Properties', 'Total Asking Price', 'Total Cost Basis', 'Total Margin', 'Portfolio Margin %'],
        [f'{total_properties_primary}', f'${total_asking_primary:,.0f}', f'${total_cost_primary:,.0f}', 
         f'${total_margin_primary:,.0f}', f'{overall_margin_pct_primary:.1f}%']
    ]
    
    primary_summary_table = Table(primary_summary_data, colWidths=[2.2*inch, 2.5*inch, 2.5*inch, 2.3*inch, 2.2*inch])
    primary_summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 1), (-1, 1), colors.lightgrey),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    
    story.append(primary_summary_table)
    story.append(Spacer(1, 28))
    
    # Add explanatory note before secondary sections
    note_style = ParagraphStyle(
        'ExplanatoryNote',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica-Oblique',
        textColor=colors.darkblue,
        spaceAfter=16,
        spaceBefore=8,
        leftIndent=20,
        rightIndent=20
    )
    
    explanatory_note = 'Note: "Listed (Secondary)" are alternative MLS or acreage-size listings for properties included in "Listed (Primary)" above.'
    story.append(Paragraph(explanatory_note, note_style))
    
    # Process secondary sections
    for section_name, status, listing_type in secondary_sections:
        # Filter data for this section
        section_df = df[
            (df['primary_opportunity_status_label'] == status) & 
            (df['custom.Asset_Listing_Type'] == listing_type)
        ].copy()
        
        if len(section_df) == 0:
            continue  # Skip empty sections
        
        # Section header
        story.append(Paragraph(section_name, section_style))
        
        # Prepare table data
        table_data = []
        
        # Improved headers with better spacing
        headers = [
            'Property Name', 'Owner', 'State', 'County', 'Acres', 
            'Date Purchased', 'Cost Basis', 'Current Price', 
            'Profit Margin', 'Margin %', 'Markup %', 
            'Price/Acre', 'Cost/Acre', 'Original Price', 
            '%OLP', 'DOM'
        ]
        table_data.append(headers)
        
        # Sort by state, then county, then property name
        section_df = section_df.sort_values(['custom.All_State', 'custom.All_County', 'display_name'])
        
        for _, row in section_df.iterrows():
            # Property name with smart wrapping
            property_name = wrap_text_smart(row.get('display_name', 'Unknown Property'), 25)
            owner = wrap_text_smart(row.get('custom.Asset_Owner', 'N/A'), 15)
            state = str(row.get('custom.All_State', 'N/A'))
            county = wrap_text_smart(row.get('custom.All_County', 'N/A'), 15)
            acres = f"{row.get('custom.All_Asset_Surveyed_Acres', 0):.1f}" if pd.notna(row.get('custom.All_Asset_Surveyed_Acres')) else 'N/A'
            
            # Format date purchased
            date_purchased = 'N/A'
            if pd.notna(row.get('custom.Asset_Date_Purchased')):
                try:
                    date_val = pd.to_datetime(row.get('custom.Asset_Date_Purchased'))
                    date_purchased = date_val.strftime('%m/%d/%Y')
                except:
                    date_purchased = str(row.get('custom.Asset_Date_Purchased'))
            
            # Format financial data
            cost_basis = f"${row.get('custom.Asset_Cost_Basis', 0):,.0f}" if pd.notna(row.get('custom.Asset_Cost_Basis')) and row.get('custom.Asset_Cost_Basis', 0) > 0 else 'N/A'
            asking_price = f"${row.get('primary_opportunity_value', 0):,.0f}" if pd.notna(row.get('primary_opportunity_value')) and row.get('primary_opportunity_value', 0) > 0 else 'N/A'
            profit_margin = f"${row.get('current_margin', 0):,.0f}" if pd.notna(row.get('current_margin')) else 'N/A'
            margin_pct = f"{row.get('current_margin_pct', 0):.0f}%" if pd.notna(row.get('current_margin_pct')) else 'N/A'
            markup = f"{row.get('markup_percentage', 0):.0f}%" if pd.notna(row.get('markup_percentage')) else 'N/A'
            price_per_acre = f"${row.get('price_per_acre', 0):,.0f}" if pd.notna(row.get('price_per_acre')) and row.get('price_per_acre', 0) > 0 else 'N/A'
            cost_per_acre = f"${row.get('cost_basis_per_acre', 0):,.0f}" if pd.notna(row.get('cost_basis_per_acre')) and row.get('cost_basis_per_acre', 0) > 0 else 'N/A'
            original_price = f"${row.get('custom.Asset_Original_Listing_Price', 0):,.0f}" if pd.notna(row.get('custom.Asset_Original_Listing_Price')) and row.get('custom.Asset_Original_Listing_Price', 0) > 0 else 'N/A'
            percent_olp = f"{row.get('percent_of_initial_listing', 0):.0f}%" if pd.notna(row.get('percent_of_initial_listing')) else 'N/A'
            dom = f"{row.get('days_on_market', 0):.0f}" if pd.notna(row.get('days_on_market')) else 'N/A'
            
            # Create table row with Paragraph objects for proper text wrapping
            table_data.append([
                Paragraph(property_name, styles['Normal']),
                Paragraph(owner, styles['Normal']),
                Paragraph(state, styles['Normal']),
                Paragraph(county, styles['Normal']),
                Paragraph(acres, styles['Normal']),
                Paragraph(date_purchased, styles['Normal']),
                Paragraph(cost_basis, styles['Normal']),
                Paragraph(asking_price, styles['Normal']),
                Paragraph(profit_margin, styles['Normal']),
                Paragraph(margin_pct, styles['Normal']),
                Paragraph(markup, styles['Normal']),
                Paragraph(price_per_acre, styles['Normal']),
                Paragraph(cost_per_acre, styles['Normal']),
                Paragraph(original_price, styles['Normal']),
                Paragraph(percent_olp, styles['Normal']),
                Paragraph(dom, styles['Normal'])
            ])
        
        if len(table_data) > 1:  # Only create table if there's data beyond headers
            # Optimized column widths for legal landscape (~13.7 inches available with narrow margins)
            col_widths = [
                1.5*inch,  # Property Name
                0.9*inch,  # Owner
                0.5*inch,  # State
                0.9*inch,  # County
                0.6*inch,  # Acres
                0.9*inch,  # Date Purchased
                0.9*inch,  # Cost Basis
                1.0*inch,  # Current Price
                0.9*inch,  # Profit Margin
                0.6*inch,  # Margin %
                0.6*inch,  # Markup %
                0.9*inch,  # Price/Acre
                0.9*inch,  # Cost/Acre
                1.0*inch,  # Original Price
                0.6*inch,  # %OLP
                0.5*inch   # DOM
            ]
            
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            # Enhanced table styling with column-specific alignment
            table.setStyle(TableStyle([
                # Header row styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                
                # Data rows styling
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                
                # Column-specific alignment for data rows
                ('ALIGN', (0, 1), (1, -1), 'LEFT'),     # Property Name and Owner - LEFT
                ('ALIGN', (2, 1), (3, -1), 'CENTER'),   # State and County - CENTER
                ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),   # All remaining columns - RIGHT
                
                ('VALIGN', (0, 1), (-1, -1), 'TOP'),   # Top align for wrapped text
                
                # Grid lines
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                
                # Alternating row colors for better readability
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                
                # Better padding for readability
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            
            story.append(table)
            story.append(Spacer(1, 20))
        
        # Enhanced section summary
        section_count = len(section_df)
        total_asking = section_df['primary_opportunity_value'].sum()
        total_cost = section_df['custom.Asset_Cost_Basis'].sum()
        total_margin = total_asking - total_cost
        margin_pct = (total_margin / total_asking * 100) if total_asking > 0 else 0
        
        summary_data = [
            ['Properties', f'{section_count}', 'Total Asking Price', f'${total_asking:,.0f}'],
            ['Total Margin', f'${total_margin:,.0f}', 'Total Cost Basis', f'${total_cost:,.0f}'],
            ['Portfolio Margin %', f'{margin_pct:.1f}%', '', '']
        ]
        
        summary_table = Table(summary_data, colWidths=[1.8*inch, 1.5*inch, 1.8*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 28))
    
    # Add the disclaimer at the end
    disclaimer_text = "Disclaimer: This data is sourced from our CRM and not our accounting software, based on then-available data. Final accounting data and results may vary slightly."
    story.append(Paragraph(disclaimer_text, disclaimer_style))
    
    # Build the PDF
    try:
        doc.build(story)
        buffer.seek(0)
        return buffer
    except Exception as e:
        st.error(f"Error generating PDF: {str(e)}")
        return None

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
        'custom.Asset_Owner': 'Owner',
        'custom.Asset_Listing_Type': 'Listing Type',
        'avg_one_time_active_opportunity_value': 'Avg One Time Active Opportunity Value'
    }
    
    # Filter to only properties with missing information
    incomplete_properties = df[df['missing_information'] != '✅ Complete'].copy()
    
    if len(incomplete_properties) == 0:
        story.append(Paragraph("🎉 Congratulations! All properties have complete data.", styles['Normal']))
        doc.build(story)
        buffer.seek(0)
        return buffer
    
    # Sort by Status first, then State, then County, then Property Name
    sort_columns = []
    
    # Add status sorting with custom order
    if 'primary_opportunity_status_label' in incomplete_properties.columns:
        # Create a status order mapping for sorting
        status_order_map = {'Purchased': 1, 'Listed': 2, 'Under Contract': 3}
        incomplete_properties['_status_sort'] = incomplete_properties['primary_opportunity_status_label'].map(status_order_map).fillna(999)
        sort_columns.append('_status_sort')
    
    if 'custom.All_State' in incomplete_properties.columns:
        sort_columns.append('custom.All_State')
    if 'custom.All_County' in incomplete_properties.columns:
        sort_columns.append('custom.All_County')
    if 'display_name' in incomplete_properties.columns:
        sort_columns.append('display_name')
    
    if sort_columns:
        incomplete_properties = incomplete_properties.sort_values(sort_columns)
        
        # Remove the temporary sort column
        if '_status_sort' in incomplete_properties.columns:
            incomplete_properties = incomplete_properties.drop('_status_sort', axis=1)
    
    # Group by Status, State and County for ultra-compact layout
    current_status = None
    current_state = None
    current_county = None
    
    for _, row in incomplete_properties.iterrows():
        status = row.get('primary_opportunity_status_label', 'Unknown Status')
        state = row.get('custom.All_State', 'Unknown State')
        county = row.get('custom.All_County', 'Unknown County')
        property_name = row.get('display_name', 'Unknown Property')
        missing_info = row.get('missing_information', '')
        
        # Add status header if changed (new top-level grouping)
        if status != current_status:
            current_status = status
            story.append(Spacer(1, 8))  # Slightly more spacing for status changes
            
            # Format status with color coding
            if status == 'Purchased':
                status_display = f"🔴 {status.upper()}"
            elif status == 'Listed':
                status_display = f"🔵 {status.upper()}"
            elif status == 'Under Contract':
                status_display = f"🟢 {status.upper()}"
            else:
                status_display = status.upper()
                
            story.append(Paragraph(f"STATUS: {status_display}", title_style))
            current_state = None  # Reset state when status changes
            current_county = None  # Reset county when status changes
        
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
    
    # Select key columns for display - REMOVED Lead Count
    desired_columns = [
        'display_name',                         # Property Name (Left)
        'id',                                   # ID for creating links
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
        
        # Create Property Name with Link column - simpler approach
        if 'display_name' in display_df.columns and 'id' in display_df.columns:
            def create_property_name(row):
                property_name = row['display_name'] if pd.notna(row['display_name']) else "Unknown Property"
                return property_name
            
            def create_link_url(row):
                property_id = row['id'] if pd.notna(row['id']) else ""
                if property_id:
                    return f"https://app.close.com/lead/{property_id}"
                else:
                    return ""
            
            # Create the clean property name and separate link columns
            display_df['Property Name'] = display_df.apply(create_property_name, axis=1)
            display_df['Close.com Link'] = display_df.apply(create_link_url, axis=1)
            
            # Remove the original columns
            display_df = display_df.drop(['display_name', 'id'], axis=1)
            
            # Reorder columns to put Property Name and Link first
            cols = list(display_df.columns)
            # Remove these columns from their current positions
            if 'Property Name' in cols:
                cols.remove('Property Name')
            if 'Close.com Link' in cols:
                cols.remove('Close.com Link')
            # Insert them at the beginning
            cols.insert(0, 'Close.com Link')
            cols.insert(0, 'Property Name')
            display_df = display_df[cols]
        
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
        
        # Rename columns for display - Property Name and Close.com Link are already named correctly
        display_df = display_df.rename(columns={
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
            'custom.Asset_Last_Mapping_Audit': 'Last Map Audit',
            'missing_information': 'Missing Information'
        })
        
        # Display table with custom CSS for column alignment - UPDATED WITHOUT Lead Count
        st.markdown("""
        <style>
        .dataframe th:nth-child(1), .dataframe td:nth-child(1) { text-align: left !important; }    /* Property Name */
        .dataframe th:nth-child(2), .dataframe td:nth-child(2) { text-align: left !important; }    /* Status */
        .dataframe th:nth-child(3), .dataframe td:nth-child(3) { text-align: left !important; }    /* State */
        .dataframe th:nth-child(4), .dataframe td:nth-child(4) { text-align: left !important; }    /* County */
        .dataframe th:nth-child(5), .dataframe td:nth-child(5) { text-align: left !important; }    /* APN */
        .dataframe th:nth-child(6), .dataframe td:nth-child(6) { text-align: right !important; }   /* Acres */
        .dataframe th:nth-child(7), .dataframe td:nth-child(7) { text-align: right !important; }   /* Current Asking Price */
        .dataframe th:nth-child(8), .dataframe td:nth-child(8) { text-align: right !important; }   /* Cost Basis */
        .dataframe th:nth-child(9), .dataframe td:nth-child(9) { text-align: right !important; }   /* Profit Margin */
        .dataframe th:nth-child(10), .dataframe td:nth-child(10) { text-align: center !important; } /* Margin */
        .dataframe th:nth-child(11), .dataframe td:nth-child(11) { text-align: center !important; } /* Markup */
        .dataframe th:nth-child(12), .dataframe td:nth-child(12) { text-align: right !important; }  /* Asking Price/Acre */
        .dataframe th:nth-child(13), .dataframe td:nth-child(13) { text-align: right !important; }  /* Cost Basis/Acre */
        .dataframe th:nth-child(14), .dataframe td:nth-child(14) { text-align: right !important; }  /* Original Listing Price */
        .dataframe th:nth-child(15), .dataframe td:nth-child(15) { text-align: center !important; } /* %OLP */
        .dataframe th:nth-child(16), .dataframe td:nth-child(16) { text-align: center !important; } /* DOM */
        .dataframe th:nth-child(17), .dataframe td:nth-child(17) { text-align: center !important; } /* Price Reductions */
        .dataframe th:nth-child(18), .dataframe td:nth-child(18) { text-align: center !important; } /* Last Map Audit */
        .dataframe th:nth-child(19), .dataframe td:nth-child(19) { text-align: left !important; }   /* Missing Information */
        </style>
        """, unsafe_allow_html=True)
        
        st.dataframe(display_df, use_container_width=True, column_config={
            "Close.com Link": st.column_config.LinkColumn(
                "Close.com Link",
                help="Click to open property in Close.com",
                display_text="🔗 Open"
            )
        })
        
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
        
        # Add Inventory Report download button
        st.subheader("📊 Download Inventory Report")
        if st.button("Generate Inventory Report", type="secondary"):
            pdf_buffer = generate_inventory_report_pdf(filtered_df)
            if pdf_buffer:
                filename = f"{datetime.now().strftime('%Y%m%d')}_Inventory_Report.pdf"
                st.download_button(
                    label="📥 Download Inventory Report",
                    data=pdf_buffer,
                    file_name=filename,
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
            
            # Owner filtering section
            st.subheader("📋 Owner Filtering")
            st.markdown("Select which owners to include in the analysis:")
            
            if 'custom.Asset_Owner' in processed_df.columns:
                # Get unique owners, excluding NaN values
                all_owners = processed_df['custom.Asset_Owner'].dropna().unique()
                all_owners = sorted([owner for owner in all_owners if str(owner) != 'nan'])
                
                if len(all_owners) > 0:
                    # Create columns for checkboxes (3 per row for better layout)
                    cols_per_row = 3
                    rows_needed = (len(all_owners) + cols_per_row - 1) // cols_per_row
                    
                    # Add "Select All" and "Deselect All" buttons
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        if st.button("✅ Select All Owners"):
                            for owner in all_owners:
                                st.session_state[f"owner_{owner}"] = True
                    with col2:
                        if st.button("❌ Deselect All Owners"):
                            for owner in all_owners:
                                st.session_state[f"owner_{owner}"] = False
                    
                    # Initialize session state for owners if not exists
                    for owner in all_owners:
                        if f"owner_{owner}" not in st.session_state:
                            st.session_state[f"owner_{owner}"] = True  # Default to checked
                    
                    # Create checkboxes for each owner
                    for i in range(rows_needed):
                        cols = st.columns(cols_per_row)
                        for j in range(cols_per_row):
                            owner_index = i * cols_per_row + j
                            if owner_index < len(all_owners):
                                owner = all_owners[owner_index]
                                owner_count = len(processed_df[processed_df['custom.Asset_Owner'] == owner])
                                with cols[j]:
                                    st.session_state[f"owner_{owner}"] = st.checkbox(
                                        f"{owner} ({owner_count} properties)",
                                        value=st.session_state[f"owner_{owner}"],
                                        key=f"checkbox_owner_{owner}"
                                    )
                    
                    # Filter data based on selected owners
                    selected_owners = [owner for owner in all_owners if st.session_state.get(f"owner_{owner}", True)]
                    
                    if selected_owners:
                        # Filter the dataframe to only include selected owners
                        filtered_df = processed_df[processed_df['custom.Asset_Owner'].isin(selected_owners)]
                        
                        st.info(f"📊 Showing data for {len(selected_owners)} selected owner(s): {', '.join(selected_owners)}")
                        st.info(f"🏠 Total properties in filtered view: {len(filtered_df)} of {len(processed_df)}")
                    else:
                        st.warning("⚠️ No owners selected. Please select at least one owner to view data.")
                        st.stop()
                else:
                    st.warning("⚠️ No owner data found in the uploaded file.")
                    filtered_df = processed_df
            else:
                st.warning("⚠️ Owner column (custom.Asset_Owner) not found in uploaded file.")
                filtered_df = processed_df
            
            st.divider()
            
            # Main hierarchy analysis
            display_hierarchy_breakdown(filtered_df)
            
            st.divider()
            
            # Visualizations
            create_visualizations(filtered_df)
            
            st.divider()
            
            # Detailed tables with filtering
            display_detailed_tables(filtered_df)
            
            # Raw data preview
            with st.expander("🔍 Raw Data Preview"):
                st.dataframe(filtered_df.head(10), use_container_width=True)
                
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
        - **Cost Basis** (custom.Asset_Cost_Basis) - *Note: Values of $0 are considered missing*
        - **Date Purchased** (custom.Asset_Date_Purchased)
        - **Original Listing Price** (custom.Asset_Original_Listing_Price)
        - **Land ID Internal URL** (custom.Asset_Land_ID_Internal_URL)
        - **Land ID Share URL** (custom.Asset_Land_ID_Share_URL)
        - **MLS#** (custom.Asset_MLS#)
        - **MLS Listing Date** (custom.Asset_MLS_Listing_Date)
        - **Last Map Audit** (custom.Asset_Last_Mapping_Audit)
        - **Street Address** (custom.Asset_Street_Address)
        - **Owner** (custom.Asset_Owner)
        - **Listing Type** (custom.Asset_Listing_Type)
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

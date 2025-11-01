import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
from io import BytesIO
try:
    from reportlab.lib.pagesizes import letter, A4, A3, landscape, legal
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
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

def calculate_days_held(row):
    """Calculate days held from acquisition date to today (or sale date if sold)"""
    try:
        purchase_date = row.get('custom.Asset_Date_Purchased')
        if pd.isna(purchase_date):
            return None
        
        purchase_dt = pd.to_datetime(purchase_date)
        
        # For now, calculate to today (can be enhanced later to use sale date if available)
        return (datetime.now() - purchase_dt).days
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
        
        # Calculate days held first
        processed_df['days_held'] = processed_df.apply(calculate_days_held, axis=1)
        
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
        basic_df['days_held'] = None
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
        status_order = ['Purchased', 'Listed', 'Under Contract', 'Off Market']
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
                    'Avg Days Held': f"{status_df['days_held'].mean():.0f}" if 'days_held' in status_df.columns and status_df['days_held'].notna().any() else 'N/A',
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
            
            status_order = ['Purchased', 'Listed', 'Under Contract', 'Off Market']
            status_counts = df['primary_opportunity_status_label'].value_counts()
            
            ordered_labels = []
            ordered_values = []
            for status in status_order:
                if status in status_counts.index:
                    ordered_labels.append(status)
                    ordered_values.append(status_counts[status])
            
            fig = px.pie(values=ordered_values, names=ordered_labels,
                        color_discrete_sequence=['#2E8B57', '#4169E1', '#FF6347', '#FFD700'])
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
    
    # Updated note style - left alignment
    note_style = ParagraphStyle(
        'ExplanatoryNote',
        parent=styles['Normal'],
        fontSize=12,  # Increased from 10
        fontName='Helvetica-Oblique',
        textColor=colors.darkblue,  # Same blue as sections
        spaceAfter=16,
        spaceBefore=8,
        alignment=0,  # Left alignment
        leftIndent=20,
        rightIndent=20
    )
    
    # Updated disclaimer style - left alignment
    disclaimer_style = ParagraphStyle(
        'DisclaimerStyle',
        parent=styles['Normal'],
        fontSize=12,  # Increased from 10 to match note
        fontName='Helvetica-Oblique',
        textColor=colors.darkblue,  # Changed from grey to blue to match note
        spaceAfter=8,
        spaceBefore=16,
        alignment=0,  # Left alignment
        leftIndent=20,
        rightIndent=20
    )
    
    # Subsection style for definitions categories
    subsection_style = ParagraphStyle(
        'SubsectionStyle',
        parent=styles['Normal'],
        fontSize=11,
        fontName='Helvetica-Bold',
        textColor=colors.darkblue,
        spaceAfter=6,
        spaceBefore=0,
        alignment=0,  # Left alignment
        leftIndent=0
    )
    
    # Normal style for definitions
    normal_style = ParagraphStyle(
        'NormalStyle',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica',
        textColor=colors.black,
        spaceAfter=4,
        spaceBefore=0,
        alignment=0,  # Left alignment
        leftIndent=12
    )
    
    # Title and date
    story.append(Paragraph("Remarkable Land LLC - Inventory Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))
    
    # Define the sections based on status and listing type
    primary_sections = [
        ("Purchased (Primary)", 'Purchased', 'Primary'),
        ("Listed (Primary)", 'Listed', 'Primary'), 
        ("Under Contract (Primary)", 'Under Contract', 'Primary'),
        ("Off Market (Primary)", 'Off Market', 'Primary')
    ]
    
    secondary_sections = [
        ("Listed (Secondary)", 'Listed', 'Secondary'),
        ("Off Market (Secondary)", 'Off Market', 'Secondary')
    ]
    
    # Process primary sections first
    primary_data_for_summary = df[
        (df['primary_opportunity_status_label'].isin(['Purchased', 'Listed', 'Under Contract', 'Off Market'])) & 
        (df['custom.Asset_Listing_Type'] == 'Primary')
    ].copy()
    
    section_count = 0
    
    for section_name, status, listing_type in primary_sections:
        # Filter data for this section
        section_df = df[
            (df['primary_opportunity_status_label'] == status) & 
            (df['custom.Asset_Listing_Type'] == listing_type)
        ].copy()
        
        if len(section_df) == 0:
            continue  # Skip empty sections
        
        # Add page break before each section (except the first one)
        if section_count > 0:
            story.append(PageBreak())
        section_count += 1
        
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
            '%OLP', 'Days Held'
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
            days_held_val = f"{row.get('days_held', 0):.0f}" if pd.notna(row.get('days_held')) else 'N/A'
            
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
                Paragraph(days_held_val, styles['Normal'])
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
        
        # Enhanced section summary - 2x4 FORMAT with Total Acres and rearranged
        section_count_props = len(section_df)
        total_asking = section_df['primary_opportunity_value'].sum()
        total_cost = section_df['custom.Asset_Cost_Basis'].sum()
        total_margin = total_asking - total_cost
        margin_pct = (total_margin / total_asking * 100) if total_asking > 0 else 0
        
        # Calculate total acres
        total_acres = section_df['custom.All_Asset_Surveyed_Acres'].sum() if 'custom.All_Asset_Surveyed_Acres' in section_df.columns else 0
        total_acres_str = f"{total_acres:,.1f}" if pd.notna(total_acres) and total_acres > 0 else "N/A"
        
        # Calculate average Days Held
        avg_days_held = section_df['days_held'].mean() if 'days_held' in section_df.columns and section_df['days_held'].notna().any() else 0
        avg_days_held_str = f"{avg_days_held:.0f}" if pd.notna(avg_days_held) and avg_days_held > 0 else "N/A"
        
        # Calculate median Days Held
        median_days_held = section_df['days_held'].median() if 'days_held' in section_df.columns and section_df['days_held'].notna().any() else 0
        median_days_held_str = f"{median_days_held:.0f}" if pd.notna(median_days_held) and median_days_held > 0 else "N/A"
        
        # Create 2x4 table layout (rearranged with Total Acres)
        summary_data = [
            ['Properties', f'{section_count_props}', 'Total Asking Price', f'${total_asking:,.0f}'],
            ['Total Acres', total_acres_str, 'Total Cost Basis', f'${total_cost:,.0f}'],
            ['Average Days Held', avg_days_held_str, 'Total Profit Margin', f'${total_margin:,.0f}'],
            ['Median Days Held', median_days_held_str, 'Portfolio Margin %', f'{margin_pct:.1f}%']
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
    
    # REMOVED page break before Primary Portfolio Summary
    
    # Enhanced primary portfolio summary (only primary sections) with NEW METRICS
    story.append(Paragraph("Primary Portfolio Summary", section_style))
    
    total_properties_primary = len(primary_data_for_summary)
    total_asking_primary = primary_data_for_summary['primary_opportunity_value'].sum()
    total_cost_primary = primary_data_for_summary['custom.Asset_Cost_Basis'].sum()
    total_margin_primary = total_asking_primary - total_cost_primary
    overall_margin_pct_primary = (total_margin_primary / total_asking_primary * 100) if total_asking_primary > 0 else 0
    
    # Calculate total acres
    total_acres_primary = primary_data_for_summary['custom.All_Asset_Surveyed_Acres'].sum() if 'custom.All_Asset_Surveyed_Acres' in primary_data_for_summary.columns else 0
    
    # Calculate average metrics
    avg_days_held_primary = primary_data_for_summary['days_held'].mean() if 'days_held' in primary_data_for_summary.columns and primary_data_for_summary['days_held'].notna().any() else 0
    avg_price_per_acre_primary = (total_asking_primary / total_acres_primary) if total_acres_primary > 0 else 0
    avg_cost_per_acre_primary = (total_cost_primary / total_acres_primary) if total_acres_primary > 0 else 0
    
    # Format values
    total_acres_str = f"{total_acres_primary:,.1f}" if total_acres_primary > 0 else "N/A"
    avg_days_held_str = f"{avg_days_held_primary:.0f}" if avg_days_held_primary > 0 else "N/A"
    avg_price_per_acre_str = f"${avg_price_per_acre_primary:,.0f}" if avg_price_per_acre_primary > 0 else "N/A"
    avg_cost_per_acre_str = f"${avg_cost_per_acre_primary:,.0f}" if avg_cost_per_acre_primary > 0 else "N/A"
    
    # Create two-row summary table
    primary_summary_data = [
        ['Total Properties', 'Total Acres', 'Total Asking Price', 'Total Cost Basis', 'Total Margin', 'Portfolio Margin %'],
        [f'{total_properties_primary}', total_acres_str, f'${total_asking_primary:,.0f}', f'${total_cost_primary:,.0f}', 
         f'${total_margin_primary:,.0f}', f'{overall_margin_pct_primary:.1f}%'],
        ['Avg Days Held', 'Avg Price/Acre', 'Avg Cost/Acre', '', '', ''],
        [avg_days_held_str, avg_price_per_acre_str, avg_cost_per_acre_str, '', '', '']
    ]
    
    primary_summary_table = Table(primary_summary_data, colWidths=[1.9*inch, 1.9*inch, 2.0*inch, 2.0*inch, 1.9*inch, 2.0*inch])
    primary_summary_table.setStyle(TableStyle([
        # First row header
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        
        # First row data
        ('BACKGROUND', (0, 1), (-1, 1), colors.lightgrey),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 11),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        ('VALIGN', (0, 1), (-1, 1), 'MIDDLE'),
        
        # Second row header (Average metrics)
        ('BACKGROUND', (0, 2), (2, 2), colors.darkgreen),
        ('TEXTCOLOR', (0, 2), (2, 2), colors.white),
        ('FONTNAME', (0, 2), (2, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (2, 2), 11),
        ('ALIGN', (0, 2), (2, 2), 'CENTER'),
        ('VALIGN', (0, 2), (2, 2), 'MIDDLE'),
        
        # Second row data
        ('BACKGROUND', (0, 3), (2, 3), colors.lightgrey),
        ('FONTNAME', (0, 3), (2, 3), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 3), (2, 3), 11),
        ('ALIGN', (0, 3), (2, 3), 'CENTER'),
        ('VALIGN', (0, 3), (2, 3), 'MIDDLE'),
        
        # Hide empty cells in second row
        ('BACKGROUND', (3, 2), (-1, 3), colors.white),
        ('GRID', (3, 2), (-1, 3), 0, colors.white),
        
        # Grid for visible cells
        ('GRID', (0, 0), (2, 3), 1, colors.black),
        ('GRID', (0, 0), (-1, 1), 1, colors.black),
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    story.append(primary_summary_table)
    story.append(Spacer(1, 28))
    
    # Add page break before secondary sections
    story.append(PageBreak())
    
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
            '%OLP', 'Days Held'
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
            days_held_val = f"{row.get('days_held', 0):.0f}" if pd.notna(row.get('days_held')) else 'N/A'
            
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
                Paragraph(days_held_val, styles['Normal'])
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
        
        # Enhanced section summary - 2x4 FORMAT with Total Acres and rearranged
        section_count_props = len(section_df)
        total_asking = section_df['primary_opportunity_value'].sum()
        total_cost = section_df['custom.Asset_Cost_Basis'].sum()
        total_margin = total_asking - total_cost
        margin_pct = (total_margin / total_asking * 100) if total_asking > 0 else 0
        
        # Calculate total acres
        total_acres = section_df['custom.All_Asset_Surveyed_Acres'].sum() if 'custom.All_Asset_Surveyed_Acres' in section_df.columns else 0
        total_acres_str = f"{total_acres:,.1f}" if pd.notna(total_acres) and total_acres > 0 else "N/A"
        
        # Calculate average Days Held
        avg_days_held = section_df['days_held'].mean() if 'days_held' in section_df.columns and section_df['days_held'].notna().any() else 0
        avg_days_held_str = f"{avg_days_held:.0f}" if pd.notna(avg_days_held) and avg_days_held > 0 else "N/A"
        
        # Calculate median Days Held
        median_days_held = section_df['days_held'].median() if 'days_held' in section_df.columns and section_df['days_held'].notna().any() else 0
        median_days_held_str = f"{median_days_held:.0f}" if pd.notna(median_days_held) and median_days_held > 0 else "N/A"
        
        # Create 2x4 table layout (rearranged with Total Acres)
        summary_data = [
            ['Properties', f'{section_count_props}', 'Total Asking Price', f'${total_asking:,.0f}'],
            ['Total Acres', total_acres_str, 'Total Cost Basis', f'${total_cost:,.0f}'],
            ['Average Days Held', avg_days_held_str, 'Total Profit Margin', f'${total_margin:,.0f}'],
            ['Median Days Held', median_days_held_str, 'Portfolio Margin %', f'{margin_pct:.1f}%']
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
    
    # Add Definitions section
    story.append(PageBreak())
    story.append(Paragraph("Definitions", section_style))
    story.append(Spacer(1, 12))
    
    # Create all definitions in a consistent two-column table format with wider columns
    definitions_data = [
        # Column headers
        [Paragraph("<b>FINANCIAL TERMS</b>", subsection_style), ''],
        
        # Financial Terms in two columns
        [Paragraph("<b>Cost Basis</b> - Total acquisition cost including purchase price, closing costs, capital improvements, and capitalized holding costs.", normal_style),
         Paragraph("<b>Price/Acre</b> - Current asking price divided by total acres.", normal_style)],
        [Paragraph("<b>Current Price / Asking Price</b> - Current listed price for the property.", normal_style),
         Paragraph("<b>Cost/Acre</b> - Cost basis divided by total acres.", normal_style)],
        [Paragraph("<b>Profit Margin</b> - Dollar amount of profit (Current Price - Cost Basis).", normal_style),
         Paragraph("<b>Original Price / Original Listing Price</b> - Initial listing price when first brought to market.", normal_style)],
        [Paragraph("<b>Margin %</b> - Profit as a percentage of the asking price.", normal_style),
         Paragraph("<b>%OLP (Percent of Original Listing Price)</b> - Current price as a percentage of original listing price.", normal_style)],
        [Paragraph("<b>Markup %</b> - Profit as a percentage of the cost basis.", normal_style), ''],
        
        # Spacing
        ['', ''],
        
        # Time & Status Terms
        [Paragraph("<b>TIME & STATUS TERMS</b>", subsection_style), ''],
        [Paragraph("<b>Days Held</b> - Total days from acquisition closing to today (or sale closing if sold).", normal_style),
         Paragraph("<b>Median Days Held</b> - Middle value of all Days Held when sorted (less affected by outliers).", normal_style)],
        [Paragraph("<b>Average Days Held</b> - Mean of all Days Held values in the section.", normal_style),
         Paragraph("<b>Price Reductions</b> - Number of price reductions (tracked by trailing digit of current price).", normal_style)],
        
        # Spacing
        ['', ''],
        
        # Status Categories
        [Paragraph("<b>STATUS CATEGORIES</b>", subsection_style), ''],
        [Paragraph("<b>Purchased</b> - Property acquired but not yet listed for sale.", normal_style),
         Paragraph("<b>Under Contract</b> - Property with executed purchase agreement, pending closing.", normal_style)],
        [Paragraph("<b>Listed</b> - Property actively marketed for sale.", normal_style),
         Paragraph("<b>Off Market</b> - Property temporarily removed from active marketing.", normal_style)],
        
        # Spacing
        ['', ''],
        
        # Listing Types and Property Information
        [Paragraph("<b>LISTING TYPES</b>", subsection_style), Paragraph("<b>PROPERTY INFORMATION</b>", subsection_style)],
        [Paragraph("<b>Primary</b> - Main listing or property designation.", normal_style),
         Paragraph("<b>APN (Assessor's Parcel Number)</b> - Unique identifier assigned by county.", normal_style)],
        [Paragraph("<b>Secondary</b> - Alternative MLS listing or acreage-size variation of a primary property.", normal_style),
         Paragraph("<b>Surveyed Acres</b> - Legally surveyed acreage of the property.", normal_style)],
        ['',
         Paragraph("<b>Portfolio Margin %</b> - Overall profit margin for all properties in the section.", normal_style)],
    ]
    
    # Create table with wider columns and reduced padding
    definitions_table = Table(definitions_data, colWidths=[3.85*inch, 3.85*inch])
    definitions_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0, colors.white),  # No borders
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        # Span section headers across both columns
        ('SPAN', (0, 0), (1, 0)),   # FINANCIAL TERMS
        ('SPAN', (0, 7), (1, 7)),   # TIME & STATUS TERMS
        ('SPAN', (0, 11), (1, 11)), # STATUS CATEGORIES
    ]))
    
    story.append(definitions_table)
    story.append(Spacer(1, 12))
    
    story.append(Spacer(1, 20))
    
    # Add the disclaimer at the end using updated style
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

# [REMAINING FUNCTIONS CONTINUE HERE - Due to length limits, I'm showing the key change]
# The remaining functions (generate_missing_fields_checklist_pdf, display_detailed_tables, main) 
# remain unchanged from the original code

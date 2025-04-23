import streamlit as st
import pandas as pd
import json
import io  # Add this import
from utils.database import get_database_connection
from utils.export import export_to_csv
from utils.color_utils import hex_to_color_name  # Import the new function
import datetime
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from utils.ftp_utils import upload_to_ftp  # Import the new FTP utility

with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Initialize authenticator
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
)

if not st.session_state.get("authentication_status"):
    # Show login form 
    authenticator.login(location='main')
    # Check authentication status after login attempt
        # Successfully authenticated, save to session state
    if st.session_state.get("authentication_status") is False:
        st.error('Username/password is incorrect')
    elif st.session_state.get("authentication_status") is None:
        st.warning('Please enter your username and password')
    
elif st.session_state.get("authentication_status") is True:

# Page configuration
    st.title("📤 Export Products")

    # Initialize database connection
    db = get_database_connection()

    # Initialize export_df as empty DataFrame to prevent NameError
    export_df = pd.DataFrame()

    # Check if we have data from Product List page or need to load from database
    if 'export_csv_data' in st.session_state:
        # Use CSV data from session state (prepared in Product List page)
        st.info("Using product data prepared from Product List page.")
        products_df = pd.read_csv(io.StringIO(st.session_state.export_csv_data))
        
        # Display preview directly without filtering
        st.subheader("Preview Export Data")
        
        # Show a more comprehensive preview of the data with useful columns
        display_cols = ['product_name', 'item_sku', 'parent_child', 'market_place_title', 'color', 'size', 'image_url']
        display_cols = [col for col in display_cols if col in products_df.columns]
        
        # If no useful columns found, just show the first 5 columns
        if not display_cols:
            display_cols = products_df.columns[:5]
        
        st.dataframe(
            products_df[display_cols],
            use_container_width=True
        )
        
        st.write(f"Found {len(products_df)} products ready for export.")
        export_df = products_df
    else:
        # Get all products from database
        products_df = db.get_all_products()
        generated_products_df = db.get_all_generated_products()
        
        # Combine datasets with a product type indicator
        if not products_df.empty:
            products_df['product_type'] = 'Regular'
            
        if not generated_products_df.empty:
            generated_products_df['product_type'] = 'Generated'
            if 'design_sku' in generated_products_df.columns:
                generated_products_df = generated_products_df.rename(columns={'design_sku': 'item_sku'})
        
        # Combine dataframes if both have data
        if not products_df.empty and not generated_products_df.empty:
            all_products_df = pd.concat([products_df, generated_products_df], ignore_index=True)
        elif not products_df.empty:
            all_products_df = products_df.copy()
        elif not generated_products_df.empty:
            all_products_df = generated_products_df.copy()
        else:
            all_products_df = pd.DataFrame()

        if all_products_df.empty:
            st.info("No products found to export. Please add products first.")
            # export_df remains an empty DataFrame here
        else:
            # Add filters for export
            st.subheader("Export Options")
            
            # Filter options
            col1, col2 = st.columns(2)
            
            with col1:
                filter_option = st.selectbox(
                    "Filter products",
                    options=["All Products", "By Product Type", "By Parent/Child", "By Category", "By Date Range"]
                )
            
            filtered_df = all_products_df.copy()
            
            if filter_option == "By Product Type":
                product_type_filter = st.selectbox(
                    "Select product type",
                    options=["All", "Regular", "Generated"]
                )
                
                if product_type_filter != "All":
                    filtered_df = filtered_df[filtered_df['product_type'] == product_type_filter]
                    
            elif filter_option == "By Parent/Child":
                parent_child_filter = st.selectbox(
                    "Select type",
                    options=["All", "Parent", "Child"]
                )
                
                if parent_child_filter != "All":
                    filtered_df = filtered_df[filtered_df['parent_child'] == parent_child_filter]
            
            elif filter_option == "By Category":
                if 'category' in filtered_df.columns:
                    categories = ["All"] + sorted(filtered_df['category'].dropna().unique().tolist())
                    category_filter = st.selectbox("Select category", options=categories)
                    
                    if category_filter != "All":
                        filtered_df = filtered_df[filtered_df['category'] == category_filter]
            
            elif filter_option == "By Date Range":
                if 'created_at' in filtered_df.columns:
                    # Convert to datetime if not already
                    if not pd.api.types.is_datetime64_dtype(filtered_df['created_at']):
                        filtered_df['created_at'] = pd.to_datetime(filtered_df['created_at'])
                    
                    min_date = filtered_df['created_at'].min().date()
                    max_date = filtered_df['created_at'].max().date()
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        start_date = st.date_input("Start date", min_date)
                    
                    with col2:
                        end_date = st.date_input("End date", max_date)
                    
                    filtered_df = filtered_df[
                        (filtered_df['created_at'].dt.date >= start_date) & 
                        (filtered_df['created_at'].dt.date <= end_date)
                    ]
            
            # Preview the data to export
            st.subheader("Preview Export Data")
            
            # Show a preview with more useful columns
            display_cols = ['id', 'product_name', 'item_sku', 'parent_child', 'product_type']
            if 'price' in filtered_df.columns:
                display_cols.append('price')
                
            st.dataframe(
                filtered_df[display_cols],
                column_config={
                    "id": "ID",
                    "product_name": "Product Name",
                    "item_sku": "SKU",
                    "parent_child": "Type",
                    "product_type": "Product Type",
                    "price": st.column_config.NumberColumn("Price", format="$%.2f"),
                },
                use_container_width=True
            )
            
            st.write(f"Found {len(filtered_df)} products matching your criteria.")
            
            # Warning: Export from this page will be simpler than from the Product List page
            st.warning("For best results with mockups separated by color, use the 'Generate CSV' button on the Product List page first.")
            
            # Process for database-loaded data, as Product List has more advanced processing
            # Define function to extract mockup URLs from JSON and create color-specific entries
            def process_mockups_by_color(row_data):
                """Extract mockup URLs from JSON and create individual entries for each color"""
                if 'mockup_urls' not in row_data or pd.isna(row_data['mockup_urls']) or not row_data['mockup_urls']:
                    return [row_data]
                
                try:
                    mockup_data = row_data['mockup_urls']
                    if isinstance(mockup_data, str) and (mockup_data.startswith('[') or mockup_data.startswith('{')):
                        mockup_json = json.loads(mockup_data)
                        
                        # Handle dictionary format: {"#color1": "url1", "#color2": "url2"}
                        if isinstance(mockup_json, dict) and len(mockup_json) > 0:
                            result_rows = []
                            
                            for color_code, mockup_url in mockup_json.items():
                                new_row = row_data.copy()
                                
                                # Set the image_url to this specific mockup URL
                                new_row['image_url'] = mockup_url
                                
                                # Convert hex to friendly color name
                                color_name = hex_to_color_name(color_code)
                                
                                # Set color value for this mockup
                                new_row['colour'] = color_name
                                new_row['color'] = color_name
                                
                                # Store original hex code for matching purposes
                                new_row['original_hex'] = color_code.replace("#", "") if color_code.startswith("#") else color_code
                                
                                result_rows.append(new_row)
                            
                            return result_rows
                            
                        # Handle array format: ["url1", "url2"]
                        elif isinstance(mockup_json, list) and len(mockup_json) > 0:
                            # For array format, we'll just use the first URL
                            # since we don't have color information
                            row_data['image_url'] = mockup_json[0]
                            return [row_data]
                except Exception as e:
                    print(f"Error processing mockups: {e}")
                
                # Default: return the original row
                return [row_data]

            # Process data for CSV formatting - process mockups intelligently
            export_rows = []
            
            for idx, row in filtered_df.iterrows():
                product_row = row.copy()
                
                # For generated products with mockups, handle them specially
                if product_row.get('product_type') == 'Generated' and 'mockup_urls' in product_row and not pd.isna(product_row['mockup_urls']) and product_row['mockup_urls']:
                    # Process mockups by color
                    color_rows = process_mockups_by_color(product_row.to_dict())
                    export_rows.extend(color_rows)
                else:
                    # Process size and color values as in the original code
                    # ...existing code for handling size and color...
                    export_rows.append(product_row.to_dict())
            
            # Convert the rows back to a DataFrame
            export_df = pd.DataFrame(export_rows)
            
            # Ensure required fields exist and add special handling for generated products
            required_fields = [
                'product_name', 'item_sku', 'parent_child', 'parent_sku',
                'size', 'color', 'image_url', 'market_place_title', 'category'
            ]
            
            for field in required_fields:
                if field not in export_df.columns:
                    export_df[field] = ''
                    
            # Special handling for generated products
            if 'product_type' in export_df.columns:
                # Set parent_child values based on product type
                # For regular products: set parent_child as "Parent" 
                mask_regular = export_df['product_type'] == 'Regular'
                if any(mask_regular):
                    export_df.loc[mask_regular, 'parent_child'] = 'Parent'
                
                # For generated products: set parent_child as "Child"
                mask_generated = export_df['product_type'] == 'Generated'
                if any(mask_generated):
                    export_df.loc[mask_generated, 'parent_child'] = 'Child'
                
                # For generated products, use product_name as category
                if any(mask_generated):
                    export_df.loc[mask_generated, 'category'] = export_df.loc[mask_generated, 'product_name']
                
                # For parent records in generated products, make item_sku blank
                mask_parent_generated = (export_df['product_type'] == 'Generated') & \
                                        (export_df['parent_child'] == 'Parent')
                if any(mask_parent_generated):
                    export_df.loc[mask_parent_generated, 'item_sku'] = ''
                    
                # Set market_place_title for generated products
                for idx, row in export_df[mask_generated].iterrows():
                    product_name = row['product_name'] if not pd.isna(row['product_name']) else ''
                    size = row['size'] if not pd.isna(row['size']) and row['size'] else ''
                    color = row['color'] if not pd.isna(row['color']) and row['color'] else ''
                    
                    # Build marketplace title with available information
                    title_parts = [part for part in [product_name, size, color] if part]
                    marketplace_title = ' - '.join(title_parts)
                    export_df.at[idx, 'market_place_title'] = marketplace_title

            # Fix for the filtered data export to properly match color-specific mockups
            if 'export_csv_data' not in st.session_state and not export_df.empty:
                # For generated products with colors, ensure the image_url matches the color
                if 'product_type' in export_df.columns and 'color' in export_df.columns and 'mockup_urls' in export_df.columns:
                    # Get all generated products with mockup_urls
                    mask_generated_with_mockups = (export_df['product_type'] == 'Generated') & (~export_df['mockup_urls'].isna()) & (export_df['mockup_urls'] != '')
                    
                    # Process each row to match color with the correct mockup URL
                    for idx, row in export_df[mask_generated_with_mockups].iterrows():
                        try:
                            # Get the color for this row
                            color = row['color'] if not pd.isna(row['color']) else None
                            if not color:
                                continue
                                
                            # Parse the mockup_urls JSON
                            if not pd.isna(row['mockup_urls']) and row['mockup_urls']:
                                mockup_data = row['mockup_urls']
                                if isinstance(mockup_data, str) and mockup_data.startswith('{'):
                                    mockup_json = json.loads(mockup_data)
                                    
                                    # Try to find matching color in the mockup_urls (different formats)
                                    # First try direct color name match if mockup_urls contains color names
                                    if color in mockup_json:
                                        export_df.at[idx, 'image_url'] = mockup_json[color]
                                        continue
                                        
                                    # Try with # prefix
                                    hex_color = f"#{color}" if not color.startswith('#') else color
                                    if hex_color in mockup_json:
                                        export_df.at[idx, 'image_url'] = mockup_json[hex_color]
                                        continue
                                    
                                    # Try without # prefix
                                    plain_color = color.replace('#', '')
                                    if plain_color in mockup_json:
                                        export_df.at[idx, 'image_url'] = mockup_json[plain_color]
                                        continue
                                        
                                    # If no direct match, look for a color name match
                                    # Convert each hex to color name and compare
                                    for hex_code, url in mockup_json.items():
                                        mockup_color_name = hex_to_color_name(hex_code)
                                        if mockup_color_name.lower() == color.lower():
                                            export_df.at[idx, 'image_url'] = url
                                            break
                        except Exception as e:
                            print(f"Error matching mockup URL for color {color}: {e}")

    # Export button
    if not export_df.empty:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"product_export_{timestamp}.csv"
        
        # Prepare CSV data - either from existing session state or by generating new
        if 'export_csv_data' in st.session_state:
            csv_data = st.session_state.export_csv_data
        else:
            # Keep only required fields + any additional useful ones
            all_fields = required_fields + [col for col in export_df.columns if col not in required_fields]
            export_df = export_df[all_fields]
            csv_data = export_to_csv(export_df)
        
        # Get FTP settings for upload option
        ftp_settings = db.get_ftp_settings()
        has_ftp_settings = not ftp_settings.empty
        
        # Check if we have default FTP settings
        default_ftp_settings = db.get_default_ftp_settings() if has_ftp_settings else None
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 Download CSV",
                data=csv_data,
                file_name=export_filename,
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Add FTP upload button if we have FTP settings
            if has_ftp_settings:
                # Select FTP server if multiple available
                if len(ftp_settings) > 1:
                    ftp_options = {}
                    for _, row in ftp_settings.iterrows():
                        label = f"{row['host']} ({row['username']})"
                        if row['is_default']:
                            label += " (Default)"
                        ftp_options[row['id']] = label
                    
                    selected_ftp_id = st.selectbox(
                        "Select FTP Server",
                        options=list(ftp_options.keys()),
                        format_func=lambda x: ftp_options[x],
                        index=0
                    )
                    
                    selected_ftp = db.get_ftp_setting(selected_ftp_id)
                else:
                    selected_ftp = default_ftp_settings
                
                if st.button("📤 Upload to FTP Server", use_container_width=True):
                    if not csv_data:
                        st.error("No data to upload. Please generate export data first.")
                    elif not selected_ftp:
                        st.error("No FTP server selected or available.")
                    else:
                        with st.spinner(f"Uploading to FTP server {selected_ftp['host']}..."):
                            success, message = upload_to_ftp(
                                csv_data, 
                                export_filename, 
                                selected_ftp
                            )
                            if success:
                                st.success(message)
                            else:
                                st.error(message)
                                st.info("You can configure FTP servers in the Settings page.")
            else:
                if st.button("📤 Configure FTP Upload", use_container_width=True):
                    # Redirect to Settings page
                    st.info("Please configure an FTP server in the Settings page first.")
                    if st.button("Go to Settings"):
                        # Use query parameters to navigate to Settings page
                        st.experimental_set_query_params(page="settings")
                        st.rerun()

    # Show export format info
    st.subheader("Export Format Information")
    st.markdown("""
    The exported CSV file follows this column structure:

    - **Product Name**: Name of the product
    - **Item SKU**: Unique product identifier (blank for parent records in generated products)
    - **Parent/Child**: Whether this is a parent or child product
    - **Parent SKU**: For child products, the SKU of the parent product
    - **Size**: Product size (if applicable)
    - **Color**: Product color (automatically converted from hex codes to friendly color names)
    - **Image URL**: URL to the product image or mockup (AWS S3 URL if cloud storage is enabled)
    - **Marketplace Title**: Full product title for marketplace listing
    - **Category**: Category path (uses product name for generated products)

    Additional fields for regular products:
    - **Tax Class**: Tax classification
    - **Qty**: Quantity in stock
    - **Price**: Product price

    > **Note:** For generated products with mockups, each color variant will have its own row with the corresponding mockup URL, making it easy to create color variations in your e-commerce platform. Hex color codes are automatically converted to friendly color names.
    """)

    # New section to explain S3 storage benefits
    st.subheader("Cloud Storage Benefits")
    st.markdown("""
    This application uses **AWS S3** for image storage, which provides several advantages:

    1. **Scalability** - Store thousands of product images efficiently
    2. **Reliability** - Highly available, durable storage with 99.999999999% durability
    3. **Cost-effective** - Only pay for what you use, typically pennies per GB for storage
    4. **Performance** - Fast image loading from AWS's global CDN network
    5. **Security** - Images can be secured with permissions while still being accessible to your store

    Your exported CSV will contain direct links to these cloud-stored images that you can use in your e-commerce platform without having to re-upload them.

    ### How It Works

    1. When you upload product images, they're stored in your S3 bucket
    2. Mockups are generated using the DynamicMockups API and also stored in S3
    3. Each color variant gets its own mockup URL in the exported CSV
    4. Your e-commerce platform can use these links directly - no need to re-upload!
    """)

    # Add info about FTP export at the bottom of the page
    st.subheader("FTP Export")
    st.markdown("""
    You can now upload your CSV exports directly to an FTP server. This allows you to:

    1. **Automate Your Workflow** - Send exports directly to your server without manual download/upload steps
    2. **Save Time** - One-click upload to your FTP server
    3. **Integrate** - Easily integrate with e-commerce and inventory systems that support FTP imports
    
    To use this feature:
    1. Go to the **Settings** page and add your FTP server credentials
    2. Return to this page and use the "Upload to FTP Server" button
    
    > **Note:** Your FTP credentials are securely stored in the database.
    """)

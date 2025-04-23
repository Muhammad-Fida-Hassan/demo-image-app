import streamlit as st
import pandas as pd
from utils.auth import check_password
from utils.database import get_database_connection
from PIL import Image
import json
from utils.api import is_s3_url
from utils.s3_storage import get_image_from_s3_url
from utils.color_utils import hex_to_color_name
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

# Page configuration
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
    authenticator.login(location='main')
    if st.session_state.get("authentication_status") is False:
        st.error('Username/password is incorrect')
    elif st.session_state.get("authentication_status") is None:
        st.warning('Please enter your username and password')

elif st.session_state.get("authentication_status") is True:
    st.title("📋 Product List")

    # Initialize database connection
    db = get_database_connection()

    # Initialize session state for delete confirmation
    if 'confirm_delete' not in st.session_state:
        st.session_state.confirm_delete = False
    if 'product_to_delete' not in st.session_state:
        st.session_state.product_to_delete = None

    # Initialize session state for viewing a single product
    if 'view_product_id' not in st.session_state:
        st.session_state.view_product_id = None
    if 'view_product_type' not in st.session_state:
        st.session_state.view_product_type = None

    # Initialize pagination state
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 1
    if 'items_per_page' not in st.session_state:
        st.session_state.items_per_page = 5

    # Get all products from database
    products_df = db.get_all_products()
    generated_products_df = db.get_all_generated_products()

    # Add a type column to distinguish between regular and generated products
    if not products_df.empty:
        products_df['product_type'] = 'Regular'

    if not generated_products_df.empty:
        generated_products_df['product_type'] = 'Generated'
        if 'design_sku' in generated_products_df.columns:
            generated_products_df = generated_products_df.rename(columns={'design_sku': 'item_sku'})

    # Handle delete confirmation modal
    if st.session_state.confirm_delete:
        product_id = st.session_state.product_to_delete
        product_type = st.session_state.product_type

        if product_type == "Regular":
            product = db.get_product(product_id)
            product_name = product['product_name']
        else:  # Generated
            product = db.get_generated_product(product_id)
            product_name = product['product_name']

        st.warning("⚠️ Delete Confirmation")
        st.write(f"Are you sure you want to delete **{product_name}**?")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Delete", type="primary"):
                success = False
                if product_type == "Regular":
                    success = db.delete_product(product_id)
                else:
                    success = db.delete_generated_product(product_id)

                if success:
                    st.session_state.confirm_delete = False
                    st.session_state.product_to_delete = None
                    st.success("Product deleted successfully!")
                    st.rerun()
                else:
                    st.error("Failed to delete product")
        with col2:
            if st.button("Cancel"):
                st.session_state.confirm_delete = False
                st.session_state.product_to_delete = None
                st.rerun()

    # Handle view single product
    elif st.session_state.view_product_id is not None:
        product_id = st.session_state.view_product_id
        product_type = st.session_state.view_product_type

        if product_type == "Regular":
            product = db.get_product(product_id)
        else:  # Generated
            product = db.get_generated_product(product_id)

        if st.button("← Back to Product List"):
            st.session_state.view_product_id = None
            st.session_state.view_product_type = None
            st.rerun()

        st.subheader(f"Product Details: {product['product_name']} ({product_type} Product)")

        size_value = 'N/A'
        color_value = 'N/A'

        if product['size']:
            try:
                if isinstance(product['size'], str) and (product['size'].startswith('[') or product['size'].startswith('{')):
                    size_data = json.loads(product['size'])
                    if isinstance(size_data, list):
                        if all(isinstance(item, dict) and 'name' in item for item in size_data):
                            size_names = [item['name'] for item in size_data]
                            size_value = ', '.join(size_names)
                        else:
                            size_value = ', '.join(str(item) for item in size_data)
                    else:
                        size_value = str(product['size'])
                else:
                    size_value = str(product['size'])
            except:
                size_value = str(product['size'])

        if product['color']:
            try:
                if isinstance(product['color'], str) and product['color'].startswith('['):
                    color_data = json.loads(product['color'])
                    if isinstance(color_data, list):
                        color_value = ', '.join(str(color) for color in color_data)
                    else:
                        color_value = str(product['color'])
                else:
                    color_value = str(product['color'])
            except:
                color_value = str(product['color'])

        product_details = {
            "Product Name": product['product_name'],
            "Size": size_value,
            "Color": color_value
        }

        if product_type == "Regular" and 'price' in product:
            product_details["Price"] = f"${product['price']}"

        if 'category' in product and product['category']:
            product_details["Category"] = product['category']

        if product_type == "Regular" and 'item_sku' in product:
            product_details["SKU"] = product['item_sku']
        elif product_type == "Generated" and 'design_sku' in product:
            product_details["Design SKU"] = product['design_sku']

        if product_type == "Generated":
            if 'is_published' in product:
                product_details["Published"] = "Yes" if product['is_published'] else "No"

        if 'created_at' in product and product['created_at']:
            product_details["Created at"] = product['created_at']

        details_df = pd.DataFrame(product_details.items(), columns=['Attribute', 'Value'])
        st.table(details_df)

        st.markdown("---")
        st.subheader("Product Images")

        if product_type == "Generated" and 'mockup_urls' in product and product['mockup_urls']:
            try:
                mockup_data = json.loads(product['mockup_urls']) if isinstance(product['mockup_urls'], str) else product['mockup_urls']
                if isinstance(mockup_data, dict) and len(mockup_data) > 0:
                    st.write("Available mockups:")
                    for color_code, urls in mockup_data.items():
                        color_key = color_code.lstrip('#')
                        color_name = hex_to_color_name(f"#{color_key}")
                        url_list = [url.strip() for url in urls.split(',')] if isinstance(urls, str) else [urls]
                        for i, url in enumerate(url_list):
                            if url:
                                try:
                                    st.image(url, caption=f"Mockup - {color_name} {i+1}", width=300)
                                except Exception as img_err:
                                    st.error(f"Failed to load image {url}: {img_err}")
                            else:
                                st.markdown(f"📷 *No valid URL for {color_name} {i+1}*")
                else:
                    st.markdown("📷 *No valid mockup images available*")
            except Exception as e:
                st.error(f"Error parsing mockup URLs: {e}")
                st.markdown("📷 *Mockup images could not be loaded*")
        else:
            image_field = 'image_url' if product_type == "Regular" else 'original_design_url'
            if image_field in product and product[image_field]:
                try:
                    st.image(product[image_field], caption=f"Image for {product['product_name']}", width=300)
                except Exception as img_err:
                    st.error(f"Failed to load image {product[image_field]}: {img_err}")
                    st.markdown("📷 *Image could not be loaded*")
            else:
                st.markdown("📷 *No image available*")

    else:
        # Add search and filter functionality
        st.subheader("Search & Filter")

        col1, col2 = st.columns(2)

        with col1:
            search_term = st.text_input("Search by name or SKU", "")

        with col2:
            categories = []
            if not products_df.empty and 'category' in products_df.columns:
                categories.extend(products_df['category'].dropna().unique().tolist())
            if not generated_products_df.empty and 'category' in generated_products_df.columns:
                categories.extend(generated_products_df['category'].dropna().unique().tolist())
            categories = ["All"] + list(set(categories))
            category_filter = st.selectbox("Filter by category", categories)

        # Add CSV export button
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Generate CSV File for All Product"):
                # Combine both DataFrames for CSV export to include regular products
                filtered_df = pd.concat([products_df, generated_products_df], ignore_index=True)

                if not filtered_df.empty:
                    if 'price' in filtered_df.columns:
                        filtered_df['price'] = pd.to_numeric(filtered_df['price'], errors='coerce').fillna(0.0)
                    if 'quantity' in filtered_df.columns:
                        filtered_df['quantity'] = pd.to_numeric(filtered_df['quantity'], errors='coerce').fillna(0).astype(int)

                    def process_mockups_by_color(row_data):
                        if 'mockup_urls' not in row_data or pd.isna(row_data['mockup_urls']) or not row_data['mockup_urls']:
                            return [row_data]
                        try:
                            mockup_data = row_data['mockup_urls']
                            if isinstance(mockup_data, str) and (mockup_data.startswith('[') or mockup_data.startswith('{')):
                                mockup_json = json.loads(mockup_data)
                                if isinstance(mockup_json, dict) and len(mockup_json) > 0:
                                    result_rows = []
                                    for color_code, mockup_url in mockup_json.items():
                                        new_row = row_data.copy()
                                        new_row['image_url'] = mockup_url
                                        color_name = hex_to_color_name(color_code)
                                        new_row['colour'] = color_name
                                        new_row['color'] = color_name
                                        new_row['original_hex'] = color_code.replace("#", "") if color_code.startswith("#") else color_code
                                        result_rows.append(new_row)
                                    return result_rows
                                elif isinstance(mockup_json, list) and len(mockup_json) > 0:
                                    row_data['image_url'] = mockup_json[0]
                                    return [row_data]
                        except Exception as e:
                            print(f"Error processing mockups: {e}")
                        return [row_data]

                    parent_rows = []
                    child_rows = []

                    for idx, row in filtered_df.iterrows():
                        product_row = row.copy()
                        if 'parent_child' in product_row and product_row['parent_child'] == 'Parent':
                            product_row['size'] = ''
                            product_row['colour'] = ''
                            product_row['color'] = ''
                            if product_row.get('product_type') == 'Generated' and 'mockup_urls' in product_row and product_row['mockup_urls']:
                                color_rows = process_mockups_by_color(product_row.to_dict())
                                parent_rows.extend(color_rows)
                            else:
                                parent_rows.append(product_row.to_dict())
                        else:
                            sizes = []
                            colors = []
                            if 'size' in product_row and not pd.isna(product_row['size']) and product_row['size']:
                                try:
                                    if isinstance(product_row['size'], str) and (product_row['size'].startswith('[') or product_row['size'].startswith('{')):
                                        size_data = json.loads(product_row['size'])
                                        if isinstance(size_data, list):
                                            if all(isinstance(item, dict) and 'name' in item for item in size_data):
                                                sizes = [item['name'] for item in size_data]
                                            else:
                                                sizes = [str(s).strip('"\'') for s in size_data]
                                        else:
                                            sizes = [str(size_data)]
                                    else:
                                        sizes = [str(product_row['size'])]
                                except:
                                    sizes = [str(product_row['size'])]
                            color_field = 'colour' if 'colour' in product_row and not pd.isna(product_row['colour']) else 'color'
                            if color_field in product_row and not pd.isna(product_row[color_field]) and product_row[color_field]:
                                try:
                                    if isinstance(product_row[color_field], str) and (product_row[color_field].startswith('[') or product_row[color_field].startswith('{')):
                                        color_data = json.loads(product_row[color_field])
                                        if isinstance(color_data, list):
                                            colors = [str(c).strip('"\'') for c in color_data]
                                        else:
                                            colors = [str(color_data)]
                                    else:
                                        colors = [str(product_row[color_field])]
                                except:
                                    colors = [str(product_row[color_field])]
                            if product_row.get('product_type') == 'Generated' and 'mockup_urls' in product_row and product_row['mockup_urls']:
                                base_rows = []
                                if sizes:
                                    for size in sizes:
                                        size_row = product_row.copy()
                                        size_row['size'] = size
                                        base_rows.append(size_row.to_dict())
                                else:
                                    base_rows.append(product_row.to_dict())
                                for base_row in base_rows:
                                    color_rows = process_mockups_by_color(base_row)
                                    child_rows.extend(color_rows)
                            else:
                                if sizes and colors:
                                    for size in sizes:
                                        for color in colors:
                                            new_row = product_row.copy().to_dict()
                                            new_row['size'] = size
                                            new_row['colour'] = color
                                            new_row['color'] = color
                                            child_rows.append(new_row)
                                elif sizes:
                                    for size in sizes:
                                        new_row = product_row.copy().to_dict()
                                        new_row['size'] = size
                                        child_rows.append(new_row)
                                elif colors:
                                    for color in colors:
                                        new_row = product_row.copy().to_dict()
                                        new_row['colour'] = color
                                        new_row['color'] = color
                                        child_rows.append(new_row)
                                else:
                                    child_rows.append(product_row.to_dict())

                    export_rows = []
                    for parent_row in parent_rows:
                        parent_sku = parent_row.get('item_sku', '')
                        matching_children = [child for child in child_rows if child.get('parent_sku', '') == parent_sku]
                        if matching_children:
                            parent_row['product_name'] = matching_children[0].get('product_name', parent_row['product_name'])
                        export_rows.append(parent_row)
                        export_rows.extend(matching_children)
                        child_rows = [child for child in child_rows if child.get('parent_sku', '') != parent_sku]
                    export_rows.extend(child_rows)

                    export_df = pd.DataFrame(export_rows)
                    required_fields = [
                        'product_name', 'item_sku', 'parent_child', 'parent_sku',
                        'size', 'color', 'image_url', 'market_place_title', 'category',
                        'price', 'quantity', 'tax_class'
                    ]
                    field_mapping = {
                        'product_name': 'product_name',
                        'item_sku': 'item_sku',
                        'design_sku': 'item_sku',
                        'parent_child': 'parent_child',
                        'parent_sku': 'parent_sku',
                        'size': 'size',
                        'colour': 'color',
                        'color': 'color',
                        'image_url': 'image_url',
                        'original_design_url': 'image_url',
                        'mockup_urls': 'image_url',
                        'market_place_title': 'market_place_title',
                        'category': 'category',
                        'price': 'price',
                        'quantity': 'quantity',
                        'tax_class': 'tax_class'
                    }

                    def extract_first_mockup(mockup_data):
                        if pd.isna(mockup_data) or not mockup_data:
                            return ''
                        try:
                            if isinstance(mockup_data, str) and (mockup_data.startswith('[') or mockup_data.startswith('{')):
                                data = json.loads(mockup_data)
                                if isinstance(data, dict) and len(data) > 0:
                                    first_color = list(data.keys())[0]
                                    urls = data[first_color]
                                    url_list = [url.strip() for url in urls.split(',')] if isinstance(urls, str) else [urls]
                                    return url_list[0] if url_list else ''
                                elif isinstance(data, list) and len(data) > 0:
                                    return data[0]
                            return mockup_data
                        except:
                            return ''

                    if 'mockup_urls' in export_df.columns and 'product_type' in export_df.columns:
                        mask_generated = export_df['product_type'] == 'Generated'
                        if 'image_url' not in export_df.columns:
                            export_df['image_url'] = ''
                        for idx, row in export_df[mask_generated].iterrows():
                            if not pd.isna(row.get('mockup_urls')) and row.get('mockup_urls'):
                                export_df.at[idx, 'image_url'] = extract_first_mockup(row['mockup_urls'])

                    standardized_df = pd.DataFrame()
                    for required_field in required_fields:
                        if required_field in export_df.columns:
                            standardized_df[required_field] = export_df[required_field]
                        else:
                            mapped = False
                            for src_field, dest_field in field_mapping.items():
                                if dest_field == required_field and src_field in export_df.columns:
                                    if src_field == 'mockup_urls' and dest_field == 'image_url':
                                        continue
                                    standardized_df[required_field] = export_df[src_field]
                                    mapped = True
                                    break
                            if not mapped:
                                standardized_df[required_field] = ''
                    
                    # Copy product_type column to standardized_df to avoid KeyError
                    if 'product_type' in export_df.columns:
                        standardized_df['product_type'] = export_df['product_type']

                    if 'product_type' in export_df.columns:
                        mask_regular = export_df['product_type'] == 'Regular'
                        if any(mask_regular):
                            standardized_df.loc[mask_regular, 'parent_child'] = 'Parent'
                        mask_generated = export_df['product_type'] == 'Generated'
                        if any(mask_generated):
                            standardized_df.loc[mask_generated, 'parent_child'] = 'Child'
                        if any(mask_regular):
                            standardized_df.loc[mask_regular, 'parent_sku'] = ''
                        
                        if any(mask_generated):
                            standardized_df.loc[mask_generated, 'category'] = standardized_df.loc[mask_generated, 'product_name']
                        
                        mask_parent_generated = (standardized_df['product_type'] == 'Generated') & (standardized_df['parent_child'] == 'Parent')
                        if any(mask_parent_generated):
                            standardized_df.loc[mask_parent_generated, 'item_sku'] = ''
                            
                        # Ensure proper parent-child relationships for generated products
                        if 'parent_id' in export_df.columns:
                            for idx, row in standardized_df[mask_generated].iterrows():
                                if idx in export_df.index and 'parent_id' in export_df.columns:
                                    parent_id = export_df.loc[idx, 'parent_id']
                                    if parent_id and not pd.isna(parent_id):
                                        parent_product = products_df[products_df['id'] == parent_id]
                                        if not parent_product.empty and 'item_sku' in parent_product.columns:
                                            standardized_df.at[idx, 'parent_sku'] = parent_product.iloc[0]['item_sku']
                            
                        if 'marketplace_title' not in standardized_df.columns or standardized_df['market_place_title'].isna().any():
                            if 'marketplace_title' not in standardized_df.columns:
                                standardized_df['market_place_title'] = ''
                            for idx, row in standardized_df[mask_generated].iterrows():
                                product_name = row['product_name'] if not pd.isna(row['product_name']) else ''
                                size = row['size'] if not pd.isna(row['size']) and row['size'] else ''
                                color = row['color'] if not pd.isna(row['color']) and row['color'] else ''
                                title_parts = [part for part in [product_name, size, color] if part]
                                marketplace_title = ' - '.join(title_parts)
                                standardized_df.at[idx, 'market_place_title'] = marketplace_title
                        if 'marketplace_title' in export_df.columns:
                            for idx, row in standardized_df[mask_generated].iterrows():
                                if idx in export_df.index and not pd.isna(export_df.at[idx, 'marketplace_title']) and export_df.at[idx, 'marketplace_title']:
                                    standardized_df.at[idx, 'market_place_title'] = export_df.at[idx, 'marketplace_title']
                        if 'image_url' in standardized_df.columns and 'color' in standardized_df.columns:
                            for idx, row in standardized_df[mask_generated].iterrows():
                                if pd.isna(row['color']) or not row['color']:
                                    continue
                                if idx in export_df.index and 'mockup_urls' in export_df.columns:
                                    mockup_urls = export_df.at[idx, 'mockup_urls']
                                    if pd.isna(mockup_urls) or not mockup_urls:
                                        continue
                                    try:
                                        if isinstance(mockup_urls, str) and (mockup_urls.startswith('{') or mockup_urls.startswith('[')):
                                            mockup_data = json.loads(mockup_urls)
                                            if isinstance(mockup_data, dict):
                                                color_val = row['color']
                                                matched = False
                                                if color_val in mockup_data:
                                                    standardized_df.at[idx, 'image_url'] = mockup_data[color_val]
                                                    matched = True
                                                if not matched and not color_val.startswith('#'):
                                                    hex_color = f"#{color_val}"
                                                    if hex_color in mockup_data:
                                                        standardized_df.at[idx, 'image_url'] = mockup_data[hex_color]
                                                        matched = True
                                                if not matched and color_val.startswith('#'):
                                                    plain_color = color_val.replace('#', '')
                                                    if plain_color in mockup_data:
                                                        standardized_df.at[idx, 'image_url'] = mockup_data[plain_color]
                                                        matched = True
                                                if not matched:
                                                    for key, url in mockup_data.items():
                                                        if key.lower() == color_val.lower() or key.lower() == f"#{color_val.lower()}" or key.lower().replace('#', '') == color_val.lower().replace('#', ''):
                                                            standardized_df.at[idx, 'image_url'] = url
                                                            matched = True
                                                            break
                                                if not matched:
                                                    color_name = row['color'].lower()
                                                    for hex_code, url in mockup_data.items():
                                                        mockup_color_name = hex_to_color_name(hex_code).lower()
                                                        if mockup_color_name == color_name:
                                                            standardized_df.at[idx, 'image_url'] = url
                                                            matched = True
                                                            break
                                    except Exception as e:
                                        print(f"Error matching mockup URL for color {row['color']}: {e}")
                        if 'parent_id' in export_df.columns:
                            for idx, row in standardized_df[mask_generated].iterrows():
                                parent_id = export_df.loc[idx, 'parent_id'] if idx in export_df.index and 'parent_id' in export_df.columns else None
                                if parent_id and not pd.isna(parent_id):
                                    parent_product = products_df[products_df['id'] == parent_id]
                                    if not parent_product.empty and 'item_sku' in parent_product.columns:
                                        standardized_df.at[idx, 'parent_sku'] = parent_product.iloc[0]['item_sku']

                    # After all rows are processed, inherit price, quantity and tax class from parents to children
                    parent_data_cache = {}
                    
                    # First collect all parent data
                    for idx, row in standardized_df.iterrows():
                        if row['parent_child'] == 'Parent' and row['item_sku']:
                            parent_data_cache[row['item_sku']] = {
                                'price': row.get('price', 0.0),
                                'quantity': row.get('quantity', 0),
                                'tax_class': row.get('tax_class', '')
                            }
                    
                    # Then update children with parent data
                    for idx, row in standardized_df.iterrows():
                        if row['parent_child'] == 'Child' and row['parent_sku'] and row['parent_sku'] in parent_data_cache:
                            parent_data = parent_data_cache[row['parent_sku']]
                            standardized_df.at[idx, 'price'] = parent_data['price']
                            standardized_df.at[idx, 'quantity'] = parent_data['quantity']
                            standardized_df.at[idx, 'tax_class'] = parent_data['tax_class']

                    column_order = required_fields + [col for col in standardized_df.columns if col not in required_fields]
                    st.session_state.export_csv_data = standardized_df[column_order].to_csv(index=False)
                else:
                    empty_df = pd.DataFrame(columns=[
                        'product_name', 'item_sku', 'parent_child', 'parent_sku',
                        'size', 'color', 'image_url', 'market_place_title', 'category'
                    ])
                    st.session_state.export_csv_data = empty_df.to_csv(index=False)

                st.success("CSV data prepared! Please proceed to the Export page to download the file.")

        # Use only generated products for display
        filtered_df = generated_products_df.copy()

        # Apply additional filters
        if not filtered_df.empty:
            if 'price' in filtered_df.columns:
                filtered_df['price'] = pd.to_numeric(filtered_df['price'], errors='coerce').fillna(0.0)
            if 'quantity' in filtered_df.columns:
                filtered_df['quantity'] = pd.to_numeric(filtered_df['quantity'], errors='coerce').fillna(0).astype(int)

            expanded_rows = []
            for idx, row in filtered_df.iterrows():
                if row.get('product_type') == 'Generated' and 'mockup_urls' in row and row['mockup_urls']:
                    try:
                        mockup_data = json.loads(row['mockup_urls']) if isinstance(row['mockup_urls'], str) else row['mockup_urls']
                        if isinstance(mockup_data, dict) and len(mockup_data) > 0:
                            for color_code, urls in mockup_data.items():
                                new_row = row.copy()
                                color_key = color_code.lstrip('#')
                                friendly_color = hex_to_color_name(f"#{color_key}")
                                url_list = [url.strip() for url in urls.split(',')] if isinstance(urls, str) else [urls]
                                first_url = url_list[0] if url_list else ''
                                new_row['current_color'] = f"#{color_key}"
                                new_row['color_name'] = friendly_color
                                new_row['current_mockup_url'] = first_url
                                if 'size' in row and row['size']:
                                    try:
                                        size_data = row['size']
                                        if isinstance(size_data, str) and (size_data.startswith('[') or size_data.startswith('{')):
                                            size_json = json.loads(size_data)
                                            if isinstance(size_json, list) and len(size_json) > 0:
                                                for size in size_json:
                                                    size_row = new_row.copy()
                                                    size_value = size
                                                    if isinstance(size, dict) and 'name' in size:
                                                        size_value = size['name']
                                                    size_row['current_size'] = size_value
                                                    expanded_rows.append(size_row)
                                                continue
                                    except Exception as e:
                                        print(f"Error processing sizes: {e}")
                                expanded_rows.append(new_row)
                            continue
                        elif isinstance(mockup_data, list) and len(mockup_data) > 0:
                            for i, mockup_url in enumerate(mockup_data):
                                new_row = row.copy()
                                new_row['current_mockup_url'] = mockup_url
                                new_row['mockup_variant'] = i + 1
                                expanded_rows.append(new_row)
                            continue
                    except Exception as e:
                        st.error(f"Error parsing mockup URLs: {e}")
                expanded_rows.append(row)

            if expanded_rows:
                filtered_df = pd.DataFrame(expanded_rows)

        # Search filter
        if search_term:
            search_columns = ['product_name', 'item_sku']
            search_mask = pd.Series(False, index=filtered_df.index)
            for col in search_columns:
                if col in filtered_df.columns:
                    search_mask |= filtered_df[col].str.contains(search_term, case=False, na=False)
            filtered_df = filtered_df[search_mask]

        # Category filter
        if category_filter != "All" and not filtered_df.empty and 'category' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['category'] == category_filter]

        # Display products
        if filtered_df.empty:
            st.info("No products found matching your criteria.")
        else:
            total_items = len(filtered_df)
            total_pages = (total_items + st.session_state.items_per_page - 1) // st.session_state.items_per_page

            if st.session_state.current_page > total_pages:
                st.session_state.current_page = total_pages
            if st.session_state.current_page < 1:
                st.session_state.current_page = 1

            start_idx = (st.session_state.current_page - 1) * st.session_state.items_per_page
            end_idx = min(start_idx + st.session_state.items_per_page, total_items)

            page_df = filtered_df.iloc[start_idx:end_idx]

            st.subheader("Products")

            # Updated table header with three columns: Image, Product Title, Action
            cols = st.columns([1, 3, 1])
            with cols[0]:
                st.markdown("**Image**")
            with cols[1]:
                st.markdown("**Product Title**")
            with cols[2]:
                st.markdown("**Action**")

            st.markdown("<hr style='margin-top: 0; margin-bottom: 10px;'>", unsafe_allow_html=True)

            for idx, row in page_df.iterrows():
                product_id = row['id']
                product_name = row['product_name']
                product_type = row['product_type']

                print(f"PRODUCT DATA: {product_type} - {product_id} - {product_name}")
                print(f"PRODUCT ROW DATA: {row}")

                # Updated row layout with three columns
                cols = st.columns([1, 3, 1])

                # Image column
                with cols[0]:
                    if product_type == 'Generated' and 'mockup_urls' in row and row['mockup_urls']:
                        try:
                            if 'current_mockup_url' in row and row['current_mockup_url']:
                                st.image(row['current_mockup_url'], width=70, caption=f"{row['color_name'] if 'color_name' in row else 'Mockup'}")
                            else:
                                mockup_data = json.loads(row['mockup_urls']) if isinstance(row['mockup_urls'], str) else row['mockup_urls']
                                if isinstance(mockup_data, dict) and len(mockup_data) > 0:
                                    first_color = list(mockup_data.keys())[0]
                                    color_key = first_color.lstrip('#')
                                    friendly_color = hex_to_color_name(f"#{color_key}")
                                    urls = mockup_data[first_color]
                                    url_list = [url.strip() for url in urls.split(',')] if isinstance(urls, str) else [urls]
                                    first_url = url_list[0] if url_list else ''
                                    if first_url:
                                        st.image(first_url, width=70, caption=f"{friendly_color}")
                                    else:
                                        st.markdown("📷 *No valid mockup image*")
                                elif isinstance(mockup_data, list) and len(mockup_data) > 0:
                                    st.image(mockup_data[0], width=70, caption="Mockup")
                                else:
                                    st.markdown("📷 *No valid mockup image*")
                        except Exception as e:
                            st.error(f"Error parsing mockup URL: {e}")
                            st.markdown("📷 *Invalid mockup data*")
                    else:
                        image_field = 'original_design_url'
                        if image_field in row and row[image_field]:
                            image_url = row[image_field]
                            if image_url and isinstance(image_url, str):
                                try:
                                    st.image(image_url, width=70, caption="Product Image")
                                except Exception as img_err:
                                    st.error(f"Failed to load image {image_url}: {img_err}")
                                    st.markdown("📷 *Image could not be loaded*")
                            else:
                                st.markdown("📷 *Invalid image URL*")
                        else:
                            st.markdown("📷 *No image available*")

                # Product name column
                with cols[1]:
                    product_name_display = product_name
                    if 'color_name' in row and row['color_name']:
                        product_name_display = f"{product_name} - {row['color_name']}"
                    if 'current_size' in row and row['current_size']:
                        product_name_display = f"{product_name_display} (Size: {row['current_size']})"
                    elif 'mockup_variant' in row:
                        product_name_display = f"{product_name_display} (Variant {row['mockup_variant']})"
                    st.write(product_name_display)

                # Action column
                with cols[2]:
                    view_col, delete_col = st.columns(2)
                    with view_col:
                        button_key_suffix = ""
                        if 'current_color' in row and row['current_color']:
                            if isinstance(row['current_color'], str):
                                button_key_suffix = f"_{row['current_color'].replace('#', '')}"
                            else:
                                button_key_suffix = f"_{str(row['current_color'])}"
                        if 'current_size' in row and row['current_size']:
                            size_str = str(row['current_size']) if row['current_size'] else ""
                            button_key_suffix = f"{button_key_suffix}_size_{size_str}"
                        elif 'mockup_variant' in row:
                            button_key_suffix = f"{button_key_suffix}_variant_{row['mockup_variant']}"
                        if st.button("View", key=f"view_{product_type}_{product_id}{button_key_suffix}"):
                            st.session_state.view_product_id = product_id
                            st.session_state.view_product_type = product_type
                            st.rerun()
                    with delete_col:
                        if st.button("Delete", key=f"delete_{product_type}_{product_id}{button_key_suffix}"):
                            st.session_state.confirm_delete = True
                            st.session_state.product_to_delete = product_id
                            st.session_state.product_type = product_type
                            st.rerun()

                st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)

            st.write("")

            col1, col2, col3 = st.columns([1, 3, 1])

            with col1:
                prev_disabled = (st.session_state.current_page <= 1)
                if st.button("← Previous", disabled=prev_disabled, key="prev_button"):
                    st.session_state.current_page -= 1
                    st.rerun()

            with col2:
                page_numbers = []
                if st.session_state.current_page > 3:
                    page_numbers.append(1)
                    if st.session_state.current_page > 4:
                        page_numbers.append("...")
                for i in range(max(1, st.session_state.current_page - 1), min(total_pages + 1, st.session_state.current_page + 2)):
                    page_numbers.append(i)
                if st.session_state.current_page < total_pages - 2:
                    if st.session_state.current_page < total_pages - 3:
                        page_numbers.append("...")
                    page_numbers.append(total_pages)
                page_cols = st.columns(len(page_numbers))
                for i, page_col in enumerate(page_cols):
                    with page_col:
                        if page_numbers[i] == "...":
                            st.write("...")
                        else:
                            page_num = page_numbers[i]
                            if page_num == st.session_state.current_page:
                                st.markdown(f"**{page_num}**")
                            else:
                                if st.button(f"{page_num}", key=f"page_{page_num}"):
                                    st.session_state.current_page = page_num
                                    st.rerun()

            with col3:
                next_disabled = (st.session_state.current_page >= total_pages)
                if st.button("Next →", disabled=next_disabled, key="next_button"):
                    st.session_state.current_page += 1
                    st.rerun()

            st.write(f"Page {st.session_state.current_page} of {total_pages} | Showing {start_idx+1}-{end_idx} of {total_items} products")
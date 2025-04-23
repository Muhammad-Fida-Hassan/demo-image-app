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
    st.title("🧾 Blank Items")

    # Initialize database connection
    db = get_database_connection()

    # Initialize session state for delete confirmation
    if 'blank_confirm_delete' not in st.session_state:
        st.session_state.blank_confirm_delete = False
    if 'blank_product_to_delete' not in st.session_state:
        st.session_state.blank_product_to_delete = None

    # Initialize session state for viewing a single product
    if 'blank_view_product_id' not in st.session_state:
        st.session_state.blank_view_product_id = None
        
    # Initialize session state for editing a product
    if 'blank_edit_product_id' not in st.session_state:
        st.session_state.blank_edit_product_id = None

    # Initialize pagination state
    if 'blank_current_page' not in st.session_state:
        st.session_state.blank_current_page = 1
    if 'blank_items_per_page' not in st.session_state:
        st.session_state.blank_items_per_page = 5

    # Get all regular products from database
    products_df = db.get_all_products()

    # Add a type column to distinguish regular products
    if not products_df.empty:
        products_df['product_type'] = 'Regular'

    # Handle delete confirmation modal
    if st.session_state.blank_confirm_delete:
        product_id = st.session_state.blank_product_to_delete

        product = db.get_product(product_id)
        product_name = product['product_name']

        st.warning("⚠️ Delete Confirmation")
        st.write(f"Are you sure you want to delete **{product_name}**?")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Delete", type="primary", key="blank_delete_confirm"):
                success = db.delete_product(product_id)

                if success:
                    st.session_state.blank_confirm_delete = False
                    st.session_state.blank_product_to_delete = None
                    st.success("Product deleted successfully!")
                    st.rerun()
                else:
                    st.error("Failed to delete product")
        with col2:
            if st.button("Cancel", key="blank_delete_cancel"):
                st.session_state.blank_confirm_delete = False
                st.session_state.blank_product_to_delete = None
                st.rerun()

    # Handle edit product
    elif st.session_state.blank_edit_product_id is not None:
        product_id = st.session_state.blank_edit_product_id
        product = db.get_product(product_id)

        if st.button("← Back to Blank Items", key="blank_edit_back_button"):
            st.session_state.blank_edit_product_id = None
            st.rerun()

        st.subheader(f"Edit Product: {product['product_name']}")
        
        with st.form("edit_product_form"):
            # Product name field
            product_name = st.text_input("Product Name", value=product['product_name'])
            
            # Price field
            price = st.number_input("Price ($)", value=float(product['price']), format="%.2f", step=0.01, min_value=0.0)
            
            # SKU field
            sku = st.text_input("SKU", value=product['item_sku'])
            
            # Category field
            category = st.text_input("Category", value=product.get('category', ''))
            
            # Size field
            size_value = product.get('size', '')
            if isinstance(size_value, str) and size_value.startswith('['):
                try:
                    size_data = json.loads(size_value)
                    if isinstance(size_data, list):
                        size_value = ', '.join(item['name'] if isinstance(item, dict) and 'name' in item else str(item) for item in size_data)
                except:
                    pass
            size = st.text_input("Size", value=size_value)
            
            # Color field
            color_value = product.get('color', '')
            if isinstance(color_value, str) and color_value.startswith('['):
                try:
                    color_data = json.loads(color_value)
                    if isinstance(color_data, list):
                        color_value = ', '.join(str(color) for color in color_data)
                except:
                    pass
            color = st.text_input("Color", value=color_value)
            
            # Image URL field
            image_url = st.text_input("Image URL", value=product.get('image_url', ''))
            
            # Display the current image if available
            if image_url:
                try:
                    st.image(image_url, caption="Current Product Image", width=200)
                except:
                    st.warning("Could not load the current image.")
            
            # Submit and cancel buttons
            col1, col2 = st.columns(2)
            with col1:
                submit_button = st.form_submit_button("Save Changes")
            with col2:
                cancel_button = st.form_submit_button("Cancel")
        
        if cancel_button:
            st.session_state.blank_edit_product_id = None
            st.rerun()
            
        if submit_button:
            # Prepare size and color data
            size_processed = json.dumps([{"name": s.strip()} for s in size.split(',')]) if size else None
            color_processed = json.dumps([c.strip() for c in color.split(',')]) if color else None
            
            # Update product data
            updated_product = {
                'product_name': product_name,
                'item_sku': sku,
                'price': price,
                'category': category,
                'size': size_processed,
                'color': color_processed,
                'image_url': image_url,
                # Preserve other fields
                'parent_child': product.get('parent_child', 'Parent'),
                'parent_sku': product.get('parent_sku', ''),
                'marketplace_title': product.get('marketplace_title', ''),
                'tax_class': product.get('tax_class', ''),
                'quantity': product.get('quantity', 0),
                'mockup_id': product.get('mockup_id', None),
                'smart_object_uuid': product.get('smart_object_uuid', None),
                'mockup_ids': product.get('mockup_ids', None),
                'smart_object_uuids': product.get('smart_object_uuids', None)
            }
            
            success = db.update_product(product_id, updated_product)
            
            if success:
                st.success("Product updated successfully!")
                st.session_state.blank_edit_product_id = None
                st.rerun()
            else:
                st.error("Failed to update product. Please try again.")

    # Handle view single product
    elif st.session_state.blank_view_product_id is not None:
        product_id = st.session_state.blank_view_product_id

        product = db.get_product(product_id)

        if st.button("← Back to Blank Items", key="blank_back_button"):
            st.session_state.blank_view_product_id = None
            st.rerun()

        st.subheader(f"Product Details: {product['product_name']} (Regular Product)")

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

        if 'price' in product:
            product_details["Price"] = f"${product['price']}"

        if 'category' in product and product['category']:
            product_details["Category"] = product['category']

        if 'item_sku' in product:
            product_details["SKU"] = product['item_sku']

        if 'created_at' in product and product['created_at']:
            product_details["Created at"] = product['created_at']

        details_df = pd.DataFrame(product_details.items(), columns=['Attribute', 'Value'])
        st.table(details_df)

        st.markdown("---")
        st.subheader("Product Images")

        if 'image_url' in product and product['image_url']:
            try:
                st.image(product['image_url'], caption=f"Image for {product['product_name']}", width=300)
            except Exception as img_err:
                st.error(f"Failed to load image {product['image_url']}: {img_err}")
                st.markdown("📷 *Image could not be loaded*")
        else:
            st.markdown("📷 *No image available*")

    else:
        st.subheader("Search & Filter")

        if st.button("← Back to All Products"):
            st.experimental_set_query_params(page="product_list")
            st.rerun()

        col1, col2 = st.columns(2)

        with col1:
            search_term = st.text_input("Search by name or SKU", "", key="blank_search")

        with col2:
            categories = []
            if not products_df.empty and 'category' in products_df.columns:
                categories = products_df['category'].dropna().unique().tolist()
            categories = ["All"] + categories
            category_filter = st.selectbox("Filter by category", categories, key="blank_category")

        filtered_df = products_df.copy()

        if not filtered_df.empty:
            if 'price' in filtered_df.columns:
                filtered_df['price'] = pd.to_numeric(filtered_df['price'], errors='coerce').fillna(0.0)
            if 'quantity' in filtered_df.columns:
                filtered_df['quantity'] = pd.to_numeric(filtered_df['quantity'], errors='coerce').fillna(0).astype(int)

        if search_term:
            search_columns = ['product_name', 'item_sku']
            search_mask = pd.Series(False, index=filtered_df.index)
            for col in search_columns:
                if col in filtered_df.columns:
                    search_mask |= filtered_df[col].str.contains(search_term, case=False, na=False)
            filtered_df = filtered_df[search_mask]

        if category_filter != "All" and not filtered_df.empty and 'category' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['category'] == category_filter]

        if filtered_df.empty:
            st.info("No products found matching your criteria.")
        else:
            total_items = len(filtered_df)
            total_pages = (total_items + st.session_state.blank_items_per_page - 1) // st.session_state.blank_items_per_page

            if st.session_state.blank_current_page > total_pages:
                st.session_state.blank_current_page = total_pages
            if st.session_state.blank_current_page < 1:
                st.session_state.blank_current_page = 1

            start_idx = (st.session_state.blank_current_page - 1) * st.session_state.blank_items_per_page
            end_idx = min(start_idx + st.session_state.blank_items_per_page, total_items)

            page_df = filtered_df.iloc[start_idx:end_idx]

            st.subheader("Regular Products")

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

                cols = st.columns([1, 3, 1])

                with cols[0]:
                    image_field = 'image_url'
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

                with cols[1]:
                    st.write(product_name)

                with cols[2]:
                    view_col, edit_col, delete_col = st.columns(3)
                    with view_col:
                        if st.button("View", key=f"blank_view_{product_id}"):
                            st.session_state.blank_view_product_id = product_id
                            st.rerun()
                    with edit_col:
                        if st.button("Edit", key=f"blank_edit_{product_id}"):
                            st.session_state.blank_edit_product_id = product_id
                            st.rerun()
                    with delete_col:
                        if st.button("Delete", key=f"blank_delete_{product_id}"):
                            st.session_state.blank_confirm_delete = True
                            st.session_state.blank_product_to_delete = product_id
                            st.rerun()

                st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)

            st.write("")

            col1, col2, col3 = st.columns([1, 3, 1])

            with col1:
                prev_disabled = (st.session_state.blank_current_page <= 1)
                if st.button("← Previous", disabled=prev_disabled, key="blank_prev_button"):
                    st.session_state.blank_current_page -= 1
                    st.rerun()

            with col2:
                page_numbers = []
                if st.session_state.blank_current_page > 3:
                    page_numbers.append(1)
                    if st.session_state.blank_current_page > 4:
                        page_numbers.append("...")
                for i in range(max(1, st.session_state.blank_current_page - 1), min(total_pages + 1, st.session_state.blank_current_page + 2)):
                    page_numbers.append(i)
                if st.session_state.blank_current_page < total_pages - 2:
                    if st.session_state.blank_current_page < total_pages - 3:
                        page_numbers.append("...")
                    page_numbers.append(total_pages)

                page_cols = st.columns(len(page_numbers))
                for i, page_col in enumerate(page_cols):
                    with page_col:
                        if page_numbers[i] == "...":
                            st.write("...")
                        else:
                            page_num = page_numbers[i]
                            if page_num == st.session_state.blank_current_page:
                                st.markdown(f"**{page_num}**")
                            else:
                                if st.button(f"{page_num}", key=f"blank_page_{page_num}"):
                                    st.session_state.blank_current_page = page_num
                                    st.rerun()

            with col3:
                next_disabled = (st.session_state.blank_current_page >= total_pages)
                if st.button("Next →", disabled=next_disabled, key="blank_next_button"):
                    st.session_state.blank_current_page += 1
                    st.rerun()

            st.write(f"Page {st.session_state.blank_current_page} of {total_pages} | Showing {start_idx+1}-{end_idx} of {total_items} products")
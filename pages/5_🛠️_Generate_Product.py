import streamlit as st
import os
import requests
import json
import random
import string
from dotenv import load_dotenv
from utils.database import get_database_connection
from utils.s3_storage import upload_image_file_to_s3, check_s3_connection
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

# Load environment variables
load_dotenv()

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
    if st.session_state.get("authentication_status") is False:
        st.error('Username/password is incorrect')
    elif st.session_state.get("authentication_status") is None:
        st.warning('Please enter your username and password')

elif st.session_state.get("authentication_status") is True:

    # Initialize set for used SKU numbers and sequence tracking in session state
    if 'used_sku_numbers' not in st.session_state:
        st.session_state.used_sku_numbers = set()
    if 'sku_sequence_number' not in st.session_state:
        st.session_state.sku_sequence_number = None

    # Function to generate a random 4-digit number
    def generate_random_sku_number():
        """Generate a random 4-digit number or increment the current one"""
        if st.session_state.sku_sequence_number is None:
            # Generate a random 4-digit number
            number = random.randint(1000, 9999)
            st.session_state.sku_sequence_number = number
        else:
            # Increment the current number
            st.session_state.sku_sequence_number += 1
            number = st.session_state.sku_sequence_number
            # Ensure the number stays within 4 digits (1000–9999)
            if number > 9999:
                number = 1000  # Reset to 1000 if exceeding 9999
                st.session_state.sku_sequence_number = number
                st.session_state.used_sku_numbers.clear()  # Clear used numbers to allow reuse

        # Ensure uniqueness within the session
        while number in st.session_state.used_sku_numbers:
            st.session_state.sku_sequence_number += 1
            number = st.session_state.sku_sequence_number
            if number > 9999:
                number = 1000
                st.session_state.sku_sequence_number = number
                st.session_state.used_sku_numbers.clear()

        st.session_state.used_sku_numbers.add(number)
        return number

    # Function to generate product SKU with a random 4-digit number
    def generate_product_sku(parent_sku=None, size=None, color=None, is_display=False):
        """Generate a unique SKU with a random 4-digit number"""
        sku = ""
        
        # Use a fixed prefix or extract from parent SKU
        if parent_sku and '-' in parent_sku:
            sku_base = parent_sku.split('-')[0].upper()
        elif parent_sku and len(parent_sku) >= 4:
            sku_base = parent_sku[:4].upper()
        else:
            sku_base = "QWER"
        
        # Get a random 4-digit number
        sku_number = generate_random_sku_number()
        
        # Get size code: use XX for XX-Large, XXX for XXX-Large, otherwise first letter
        size_letter = ""
        if size:
            if size == "XX-Large":
                size_letter = "XX"
            elif size == "XXX-Large":
                size_letter = "XXX"
            else:
                size_letter = size[0].upper()  # First letter of the size
        
        # Use the provided color name, if available
        color_name = color if color else ""
        
        # Construct the SKU: QWER-4567-S-Black
        sku = f"{sku_base}-{sku_number:04d}"
        if size_letter:
            sku += f"-{size_letter}"
        if color_name:
            sku += f"-{color_name}"
        
        # If this is for display only, remove the number from used set to allow reuse
        if is_display:
            st.session_state.used_sku_numbers.discard(sku_number)
        
        return sku

    # Function to generate SKU for new products in the products table
    def generate_new_product_sku(parent_sku=None):
        """Generate a unique SKU for a new product based on product count in the database"""
        db = get_database_connection()
        
        # Extract prefix from parent SKU or use default
        if parent_sku and '-' in parent_sku:
            sku_base = parent_sku.split('-')[0].upper()
        elif parent_sku and len(parent_sku) >= 4:
            sku_base = parent_sku[:4].upper()
        else:
            sku_base = "QWER"  # Default prefix if no parent SKU is provided
        
        # Get the total number of products and increment by 1
        product_count = db.get_product_count()
        sku_number = product_count + 1
        
        # Generate the SKU with 4-digit padding
        sku = f"{sku_base}-{sku_number:04d}"
        
        # Check if the SKU already exists in the products table
        while db.execute_query("SELECT 1 FROM products WHERE item_sku = %s", (sku,)):
            sku_number += 1
            sku = f"{sku_base}-{sku_number:04d}"
        
        return sku

    # Function to update the SKU based on current form inputs
    def update_design_sku():
        """Update the design SKU based on current form inputs"""
        parent_sku = ""
        if st.session_state.selected_product_data and 'item_sku' in st.session_state.selected_product_data:
            parent_sku = st.session_state.selected_product_data['item_sku']
        
        colors = st.session_state.selected_colors if 'selected_colors' in st.session_state else []
        sizes = st.session_state.selected_sizes if 'selected_sizes' in st.session_state else []
        
        # Generate the new SKU for display using the first size and color
        new_sku = generate_product_sku(
            parent_sku=parent_sku,
            size=sizes[0] if sizes else None,
            color=colors[0] if colors else None,
            is_display=True
        )
        
        # Update the session state
        st.session_state.design_sku = new_sku
        return new_sku

    db = get_database_connection()

    # Initialize session state for delete confirmation
    if 'confirm_delete' not in st.session_state:
        st.session_state.confirm_delete = False
    if 'product_to_delete' not in st.session_state:
        st.session_state.product_to_delete = None
    if 'mockup_results' not in st.session_state:
        st.session_state.mockup_results = None

    # Get all products from database
    products_df = db.get_all_products()
    print("Products DataFrame:", products_df)

    # Initialize session state for selected product
    if 'selected_product_id' not in st.session_state:
        st.session_state.selected_product_id = None
    if 'selected_product_data' not in st.session_state:
        st.session_state.selected_product_data = None
    if 'refresh_product_selector' not in st.session_state:
        st.session_state.refresh_product_selector = False

    # Define the available options for sizes and colors
    AVAILABLE_SIZES = ["Small", "Medium", "Large", "X-Large", "XX-Large", "XXX-Large"]
    AVAILABLE_COLORS = ["Black", "Navy", "Grey", "White", "Red", "Blue", "Green", "Yellow", "Purple"]

    def check_for_matching_generated_products(item_sku):
        """
        Check if there are any generated products with parent_sku matching the given item_sku
        
        Args:
            item_sku (str): SKU to check against parent_sku in generated_products
            
        Returns:
            list: List of matching generated products, or empty list if none found
        """
        try:
            query = "SELECT * FROM generated_products WHERE parent_sku = %s ORDER BY id DESC"
            matching_products = db.execute_query(query, (item_sku,))
            return matching_products if matching_products else []
        except Exception as e:
            st.error(f"Error checking for matching generated products: {str(e)}")
            return []

    def create_new_product_from_generated(product_data):
        """
        Create a new product based on the selected product but with a new SKU
        
        Args:
            product_data (dict): Original product data
            
        Returns:
            int: ID of the newly created product or None if failed
        """
        try:
            # Check if a new product has already been created for this session
            if 'new_product_id' in st.session_state:
                return st.session_state.new_product_id

            # Generate a new unique SKU using the product count
            original_sku = product_data['item_sku']
            new_sku = generate_new_product_sku(parent_sku=original_sku)
            
            # Create a copy of product data with a new SKU
            new_product = product_data.copy()
            new_product['item_sku'] = new_sku
            
            # Remove ID to ensure it creates a new record
            if 'id' in new_product:
                del new_product['id']
            
            # Update name to indicate it's a new version
            new_product['product_name'] = f"{product_data['product_name']} (Version {new_sku.split('-')[1]})"
            
            # Insert the new product into the database
            new_id = db.add_product(new_product)
            
            if new_id:
                # Store the new product ID in session state to prevent duplicates
                st.session_state.new_product_id = new_id
                # Refresh products dataframe to include the new product
                global products_df
                products_df = db.get_all_products()
                # Trigger a refresh of the product selector
                st.session_state.refresh_product_selector = True
                return new_id
            else:
                st.error("Failed to create new product version.")
                return None
        except Exception as e:
            st.error(f"Error creating new product version: {str(e)}")
            return None

    def generate_mockup(image_url, colors, mockup_id=None, smart_object_uuid=None):
        """
        Generate multiple mockups using the Dynamic Mockups API
        
        Args:
            image_url (str): URL of the image uploaded to S3
            colors (list): List of colors for the mockups in hex format
            mockup_id (str): Optional mockup ID to use (from selected product)
            smart_object_uuid (str): Optional smart object UUID to use (from selected product)
            
        Returns:
            list: List of mockup data if successful, empty list otherwise
        """
        MOCKUP_UUID = mockup_id or "db90556b-96a3-483c-ba88-557393b992a1"
        SMART_OBJECT_UUID = smart_object_uuid or "fb677f24-3dce-4d53-b024-26ea52ea43c9"
        
        if not image_url:
            st.error("No image URL provided for mockup generation")
            return []
            
        try:
            image_check = requests.head(image_url)
            if image_check.status_code != 200:
                st.error(f"Image URL is not accessible: {image_url}")
                st.error(f"Status code: {image_check.status_code}")
                return []
        except Exception as e:
            st.error(f"Error validating image URL: {e}")
            return []
        
        mockup_results = []
        
        for color in colors:
            request_data = {
                "mockup_uuid": MOCKUP_UUID,
                "smart_objects": [
                    {
                        "uuid": SMART_OBJECT_UUID,
                        "color": color,
                        "asset": {
                            "url": image_url
                        }
                    }
                ],
                "format": "png",
                "width": 1500,
                "transparent_background": True
            }        
            try:
                response = requests.post(
                    'https://app.dynamicmockups.com/api/v1/renders',
                    json=request_data,
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'x-api-key': os.getenv('DYNAMIC_MOCKUPS_API_KEY'),
                    },
                )
                
                if response.status_code != 200:
                    st.error(f"API returned error status: {response.status_code}")
                    st.error(f"Response content: {response.text}")
                    continue
                    
                result = response.json()
                
                if 'data' in result and 'export_path' in result['data']:
                    mockup_data = {
                        'rendered_image_url': result['data']['export_path'],
                        'color': color
                    }
                    mockup_results.append(mockup_data)
                else:
                    st.error("Expected 'data.export_path' in API response but it was not found")
                    
            except Exception as e:
                st.error(f"Error generating mockup: {e}")
        
        return mockup_results

    def color_name_to_hex(color_name):
        """
        Convert common color names to their hex values
        """
        color_map = {
            "Black": "#000000",
            "White": "#FFFFFF",
            "Navy": "#000080",
            "Grey": "#808080",
            "Red": "#FF0000",
            "Blue": "#0000FF",
            "Green": "#008000",
            "Yellow": "#FFFF00",
            "Purple": "#800080"
        }
        return color_map.get(color_name, "#FF0000")

    def hex_to_color_name(hex_color):
        """Convert a hex color value to a color name"""
        hex_color = hex_color.upper().lstrip('#')
        hex_to_name = {
            "000000": "Black",
            "FFFFFF": "White",
            "000080": "Navy",
            "808080": "Grey",
            "FF0000": "Red",
            "0000FF": "Blue",
            "008000": "Green",
            "FFFF00": "Yellow",
            "800080": "Purple"
        }
        return hex_to_name.get(hex_color, None)

    def load_product_data():
        """Load product data if an item is selected from the dropdown"""
        if st.session_state.product_selector and st.session_state.product_selector != "None":
            selected_id = int(st.session_state.product_selector)
            
            # Avoid re-processing if the same product is already selected
            if st.session_state.selected_product_id == selected_id:
                return
            
            st.session_state.selected_product_id = selected_id
            
            product_data = db.get_product(selected_id)
            if product_data:
                # Check if this product's SKU matches any parent_sku in generated_products
                if 'item_sku' in product_data and product_data['item_sku']:
                    matching_generated_products = check_for_matching_generated_products(product_data['item_sku'])
                    if matching_generated_products:
                        # Automatically create a new product version with updated SKU
                        with st.spinner("Creating new product version based on existing designs..."):
                            new_product_id = create_new_product_from_generated(product_data)
                            if new_product_id:
                                # Update the selected product to the new one
                                st.session_state.selected_product_id = new_product_id
                                st.session_state.product_selector = str(new_product_id)  # Update dropdown
                                st.success(f"✅ Created new product version (ID: {new_product_id}) based on existing designs")
                                # Refresh product data for the new product
                                product_data = db.get_product(new_product_id)
                                if not product_data:
                                    st.error(f"Failed to fetch new product with ID {new_product_id}")
                                    return
                
                st.session_state.selected_product_data = product_data
                
                try:
                    if product_data['size'] and product_data['size'].startswith('['):
                        st.session_state.parsed_sizes = json.loads(product_data['size'])
                    else:
                        st.session_state.parsed_sizes = []
                        
                    if product_data['color'] and product_data['color'].startswith('['):
                        st.session_state.parsed_colors = json.loads(product_data['color'])
                    else:
                        st.session_state.parsed_colors = []
                    
                    if 'mockup_ids' in product_data and product_data['mockup_ids'] and product_data['mockup_ids'].startswith('['):
                        st.session_state.mockup_ids = json.loads(product_data['mockup_ids'])
                        print(f"Loaded multiple mockup IDs: {st.session_state.mockup_ids}")
                    else:
                        st.session_state.mockup_ids = [product_data['mockup_id']] if product_data['mockup_id'] else []
                        print(f"Using single mockup ID: {st.session_state.mockup_ids}")
                    
                    if 'smart_object_uuids' in product_data and product_data['smart_object_uuids'] and product_data['smart_object_uuids'].startswith('['):
                        st.session_state.smart_object_uuids = json.loads(product_data['smart_object_uuids'])
                        print(f"Loaded multiple smart object UUIDs: {st.session_state.smart_object_uuids}")
                    else:
                        st.session_state.smart_object_uuids = [product_data['smart_object_uuid']] if product_data['smart_object_uuid'] else []
                        print(f"Using single smart object UUID: {st.session_state.smart_object_uuids}")
                    
                    # Update design SKU based on new product data
                    update_design_sku()
                
                except json.JSONDecodeError as e:
                    st.error(f"Failed to parse product data: {e}")
                    st.session_state.parsed_sizes = []
                    st.session_state.parsed_colors = []
                    st.session_state.mockup_ids = []
                    st.session_state.smart_object_uuids = []
                except Exception as e:
                    st.error(f"Unexpected error loading product data: {str(e)}")
                    st.session_state.parsed_sizes = []
                    st.session_state.parsed_colors = []
                    st.session_state.mockup_ids = []
                    st.session_state.smart_object_uuids = []
            else:
                st.error(f"Failed to fetch product with ID {selected_id}")
                st.session_state.selected_product_data = None
        else:
            st.session_state.selected_product_id = None
            st.session_state.selected_product_data = None
            st.session_state.mockup_ids = []
            st.session_state.smart_object_uuids = []
            st.session_state.parsed_sizes = []
            st.session_state.parsed_colors = []

    def get_valid_sizes_from_parsed(parsed_sizes):
        """Extract valid size names that match our available options"""
        if not parsed_sizes:
            return []
        
        size_lookup = {s.lower(): s for s in AVAILABLE_SIZES}
        
        valid_sizes = []
        for size in parsed_sizes:
            if 'name' in size:
                size_name = size['name']
                if size_name in AVAILABLE_SIZES:
                    valid_sizes.append(size_name)
                elif size_name.lower() in size_lookup:
                    valid_sizes.append(size_lookup[size_name.lower()])
        
        return valid_sizes

    def get_valid_colors_from_parsed(parsed_colors):
        """Extract valid color names that match our available options"""
        if not parsed_colors:
            return []
        
        valid_colors = []
        
        if isinstance(parsed_colors, list) and all(isinstance(c, str) for c in parsed_colors):
            for hex_value in parsed_colors:
                color_name = hex_to_color_name(hex_value)
                if color_name and color_name in AVAILABLE_COLORS:
                    valid_colors.append(color_name)
        else:
            color_lookup = {c.lower(): c for c in AVAILABLE_COLORS}
            
            for color in parsed_colors:
                if isinstance(color, dict) and 'name' in color:
                    color_name = color['name']
                    if color_name in AVAILABLE_COLORS:
                        valid_colors.append(color_name)
                    elif color_name.lower() in color_lookup:
                        valid_colors.append(color_lookup[color_name.lower()])
        
        return valid_colors

    # Initialize session state for tracking preview dropdown colors
    if 'preview1_selected_color' not in st.session_state:
        st.session_state.preview1_selected_color = None
    if 'preview2_selected_color' not in st.session_state:
        st.session_state.preview2_selected_color = None
    if 'preview3_selected_color' not in st.session_state:
        st.session_state.preview3_selected_color = None

    # Initialize session state for tracking design image
    if 'design_image_data' not in st.session_state:
        st.session_state.design_image_data = None

    def on_file_upload():
        """Callback for when a file is uploaded"""
        if st.session_state.design_image is not None:
            st.session_state.design_image_data = st.session_state.design_image

    # Define session state variables for multiple mockup handling
    if 'mockup_ids' not in st.session_state:
        st.session_state.mockup_ids = []
    if 'smart_object_uuids' not in st.session_state:
        st.session_state.smart_object_uuids = []
    if 'active_mockup_index' not in st.session_state:
        st.session_state.active_mockup_index = 0
    if 'mockup_results_all' not in st.session_state:
        st.session_state.mockup_results_all = []
    if 'mockup_generation_progress' not in st.session_state:
        st.session_state.mockup_generation_progress = 0
    if 'template_color_index' not in st.session_state:
        st.session_state.template_color_index = None

    def generate_single_mockup(image_url, color, mockup_id=None, smart_object_uuid=None):
        """
        Generate a single mockup using the Dynamic Mockups API
        
        Args:
            image_url (str): URL of the image to use for the mockup
            color (str): Hex color code for the mockup
            mockup_id (str, optional): ID of the mockup to use
            smart_object_uuid (str, optional): UUID of the smart object to use
            
        Returns:
            dict: Mockup data if successful, None otherwise
        """
        MOCKUP_UUID = mockup_id or "db90556b-96a3-483c-ba88-557393b992a1"
        SMART_OBJECT_UUID = smart_object_uuid or "fb677f24-3dce-4d53-b024-26ea52ea43c9"
        
        try:
            request_data = {
                "mockup_uuid": MOCKUP_UUID,
                "smart_objects": [
                    {
                        "uuid": SMART_OBJECT_UUID,
                        "color": color,
                        "asset": {
                            "url": image_url
                        }
                    }
                ],
                "format": "png",
                "width": 1500,
                "transparent_background": True
            }
            
            response = requests.post(
                'https://app.dynamicmockups.com/api/v1/renders',
                json=request_data,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'x-api-key': os.getenv('DYNAMIC_MOCKUPS_API_KEY'),
                },
            )
            
            if response.status_code != 200:
                st.error(f"API returned error status: {response.status_code}")
                st.error(f"Response content: {response.text}")
                return None
                
            result = response.json()
            
            if 'data' in result and 'export_path' in result['data']:
                mockup_data = {
                    'rendered_image_url': result['data']['export_path'],
                    'color': color
                }
                return mockup_data
            else:
                st.error("Expected 'data.export_path' in API response but it was not found")
                return None
                
        except Exception as e:
            st.error(f"Error generating mockup: {e}")
            return None

    def generate_all_mockups(image_url, colors):
        """
        Generate mockups for all selected mockups
        
        Args:
            image_url (str): URL of the image uploaded to S3
            colors (list): List of colors for the mockups in hex format
            
        Returns:
            list: List of mockup data for all generated mockups
        """
        import time
        
        all_results = []
        mockup_ids = st.session_state.mockup_ids if hasattr(st.session_state, 'mockup_ids') else []
        smart_object_uuids = st.session_state.smart_object_uuids if hasattr(st.session_state, 'smart_object_uuids') else []
        
        total_mockups = len(mockup_ids)
        if total_mockups == 0:
            st.error("No mockup templates available. Please select a product with mockup templates.")
            return []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        st.info(f"Processing {total_mockups} mockup templates with {len(colors)} colors each")
        st.write(f"Mockup IDs: {mockup_ids}")
        st.write(f"Smart Object UUIDs: {smart_object_uuids}")
        
        if len(smart_object_uuids) < total_mockups:
            st.warning(f"Not enough smart object UUIDs ({len(smart_object_uuids)}) for all mockups ({total_mockups}). Some will use default smart objects.")
            smart_object_uuids = smart_object_uuids + [None] * (total_mockups - len(smart_object_uuids))
        
        mockup_count = 0
        total_progress_steps = total_mockups * len(colors)
        
        for i, (mockup_id, smart_object_uuid) in enumerate(zip(mockup_ids, smart_object_uuids)):
            progress = (i / total_mockups)
            progress_bar.progress(progress)
            status_text.text(f"Processing mockup template {i+1} of {total_mockups}: {mockup_id}")
            
            if not mockup_id:
                st.warning(f"Skipping mockup {i+1} because no valid mockup ID was found.")
                continue
            
            st.info(f"Generating mockups for template {i+1}: {mockup_id} with smart object: {smart_object_uuid}")
            
            mockup_results = []
            for j, color in enumerate(colors):
                sub_status = st.empty()
                sub_status.text(f"Generating color {j+1}/{len(colors)}: {color}")
                
                result = generate_single_mockup(
                    image_url,
                    color,
                    mockup_id=mockup_id,
                    smart_object_uuid=smart_object_uuid
                )
                
                if result:
                    mockup_results.append(result)
                    mockup_count += 1
                else:
                    st.warning(f"Failed to generate mockup for template {mockup_id} with color {color}")
                
                current_progress = (i * len(colors) + j + 1) / total_progress_steps
                progress_bar.progress(min(current_progress, 1.0))
                
                sub_status.empty()
            
            if mockup_results:
                all_results.append({
                    'mockup_id': mockup_id,
                    'smart_object_uuid': smart_object_uuid,
                    'results': mockup_results
                })
                st.success(f"Generated {len(mockup_results)} color variations for template {mockup_id}")
        
        progress_bar.progress(1.0)
        status_text.text(f"Successfully generated {mockup_count} mockups across {len(all_results)} templates!")
        time.sleep(1)
        status_text.empty()
        
        return all_results

    # Initialize session state for tracking product data to save
    if 'product_data_to_save' not in st.session_state:
        st.session_state.product_data_to_save = None
    if 'original_design_url' not in st.session_state:
        st.session_state.original_design_url = None

    # Initialize session state for color selection and on-demand mockup generation
    if 'mockup_results' not in st.session_state:
        st.session_state.mockup_results = None
    if 'on_demand_colors' not in st.session_state:
        st.session_state.on_demand_colors = []
    if 'uploaded_image_url' not in st.session_state:
        st.session_state.uploaded_image_url = None

    def generate_on_demand_mockup(color_name):
        """Generate a mockup for a specific color on-demand when selected from dropdown"""
        if not st.session_state.uploaded_image_url:
            st.warning("Please upload an image first before generating mockups.")
            return False
            
        hex_color = color_name_to_hex(color_name)
        
        if st.session_state.mockup_results and hex_color in st.session_state.mockup_results:
            return True
            
        mockup_id = None
        smart_object_uuid = None
        if st.session_state.selected_product_data:
            mockup_id = st.session_state.selected_product_data.get('mockup_id')
            smart_object_uuid = st.session_state.selected_product_data.get('smart_object_uuid')
        
        with st.spinner(f"Generating mockup for slightly modified version of {color_name}..."):
            mockup_results = generate_mockup(
                st.session_state.uploaded_image_url,
                [hex_color],
                mockup_id=mockup_id,
                smart_object_uuid=smart_object_uuid
            )
            
            if mockup_results:
                if not st.session_state.mockup_results:
                    st.session_state.mockup_results = {}
                    
                st.session_state.mockup_results[hex_color] = mockup_results[0]['rendered_image_url']
                
                if hasattr(st.session_state, 'replaced_color') and st.session_state.replaced_color:
                    if st.session_state.replaced_color != hex_color:
                        if st.session_state.replaced_color in st.session_state.mockup_results:
                            del st.session_state.mockup_results[st.session_state.replaced_color]
                    
                    st.session_state.replaced_color = None
                
                st.success(f"Generated mockup for {color_name}")
                return True
            else:
                st.error(f"Failed to generate mockup for {color_name}")
                return False

    def on_color_change(key_prefix):
        """Callback for when a color is changed in dropdown"""
        color_key = f"{key_prefix}_color"
        if color_key in st.session_state:
            selected_color = st.session_state[color_key]
            generate_on_demand_mockup(selected_color)

    # Initialize specific session state variables for tracking mockup panel selections
    if 'mockup_panel_colors' not in st.session_state:
        st.session_state.mockup_panel_colors = {}
    if 'generate_for_panel' not in st.session_state:
        st.session_state.generate_for_panel = None
    if 'generate_color' not in st.session_state:
        st.session_state.generate_color = None

    def on_mockup_color_change(mockup_idx):
        """Handle color change in the mockup preview panel"""
        if mockup_idx not in st.session_state.panel_color_mapping:
            return
            
        preview_key = f"preview_{mockup_idx}_color"
        selected_color = st.session_state[preview_key]
        hex_selected = color_name_to_hex(selected_color)
        
        st.session_state.mockup_panel_colors[mockup_idx] = selected_color
        
        if hex_selected not in st.session_state.mockup_results:
            if st.session_state.generate_for_panel is None:
                st.session_state.generate_for_panel = mockup_idx
                st.session_state.generate_color = selected_color
                original_hex = st.session_state.panel_color_mapping.get(mockup_idx)
                if original_hex:
                    st.session_state.replaced_color = original_hex
        else:
            original_hex = st.session_state.panel_color_mapping.get(mockup_idx)
            if original_hex and original_hex != hex_selected:
                st.session_state.panel_color_mapping[mockup_idx] = hex_selected

    # Initialize session state for color mappings
    if 'original_mockup_colors' not in st.session_state:
        st.session_state.original_mockup_colors = {}
    if 'panel_color_mapping' not in st.session_state:
        st.session_state.panel_color_mapping = {}

    if 'template_generate_mockup' not in st.session_state:
        st.session_state.template_generate_mockup = None
    if 'template_generate_color' not in st.session_state:
        st.session_state.template_generate_color = None
        
    def generate_template_mockup_on_demand(template_idx, color_name):
        """Generate a mockup for a specific template and color on demand"""
        if not st.session_state.uploaded_image_url:
            st.warning("Please upload an image first before generating mockups.")
            return False
            
        if not hasattr(st.session_state, 'mockup_results_all') or len(st.session_state.mockup_results_all) <= template_idx:
            st.error(f"Template {template_idx + 1} data not found.")
            return False
        
        template = st.session_state.mockup_results_all[template_idx]
        mockup_id = template['mockup_id']
        smart_object_uuid = template.get('smart_object_uuid')
        
        hex_color = color_name_to_hex(color_name)
        
        existing_index = None
        if 'results' in template:
            for i, result in enumerate(template['results']):
                if result['color'] == hex_color:
                    return True
        
        color_index = st.session_state.get('template_color_index')
        
        with st.spinner(f"Generating {color_name} mockup for Template {template_idx + 1}..."):
            result = generate_single_mockup(
                st.session_state.uploaded_image_url,
                hex_color,
                mockup_id=mockup_id,
                smart_object_uuid=smart_object_uuid
            )
            
            if result:
                if 'results' not in template:
                    template['results'] = []
                
                if color_index is not None and color_index < len(template['results']):
                    template['results'][color_index] = result
                    st.success(f"Replaced {color_name} mockup for Template {template_idx + 1}")
                else:
                    template['results'].append(result)
                    st.success(f"Generated new {color_name} mockup for Template {template_idx + 1}")
                
                st.session_state.mockup_results_all[template_idx] = template
                
                if 'template_color_index' in st.session_state:
                    del st.session_state.template_color_index
                    
                return True
            else:
                st.error(f"Failed to generate {color_name} mockup for Template {template_idx + 1}")
                return False

    def on_template_color_change(template_idx, color_index):
        """Handle color change in the template mockup preview"""
        if not hasattr(st.session_state, 'mockup_results_all') or len(st.session_state.mockup_results_all) <= template_idx:
            return
            
        color_key = f"template_{template_idx}_color_{color_index}"
        if color_key not in st.session_state:
            return
            
        selected_color = st.session_state[color_key]
        hex_selected = color_name_to_hex(selected_color)
        
        template = st.session_state.mockup_results_all[template_idx]
        mockup_exists = False
        
        if 'results' in template:
            for result in template['results']:
                if result['color'] == hex_selected:
                    mockup_exists = True
                    break
        
        if not mockup_exists:
            st.session_state.template_generate_mockup = template_idx
            st.session_state.template_generate_color = selected_color
            st.session_state.template_color_index = color_index

        # Update the design SKU to reflect the selected color
        parent_sku = ""
        if st.session_state.selected_product_data and 'item_sku' in st.session_state.selected_product_data:
            parent_sku = st.session_state.selected_product_data['item_sku']
        
        sizes = st.session_state.selected_sizes if 'selected_sizes' in st.session_state else []
        
        new_sku = generate_product_sku(
            parent_sku=parent_sku,
            size=sizes[0] if sizes else None,
            color=selected_color,
            is_display=True
        )
        
        st.session_state.design_sku = new_sku

    def generate_product_page():
        st.title("Generate Product")

        if not products_df.empty and 'id' in products_df.columns and 'product_name' in products_df.columns:
            product_options = {"None": "None"}
            product_id_to_index = {"None": 0}  # Map product IDs to their indices
            for idx, row in enumerate(products_df.iterrows(), 1):
                row = row[1]
                product_options[str(row['id'])] = f"{row['product_name']} (ID: {row['id']})"
                product_id_to_index[str(row['id'])] = idx
            
            # Handle refresh after new product creation
            if st.session_state.refresh_product_selector and 'new_product_id' in st.session_state:
                selected_id = str(st.session_state.new_product_id)
                st.session_state.product_selector = selected_id
                st.session_state.refresh_product_selector = False
                del st.session_state.new_product_id  # Clear to prevent re-use
            else:
                selected_id = str(st.session_state.selected_product_id) if st.session_state.selected_product_id else "None"
            
            selected_index = product_id_to_index.get(selected_id, 0)
            
            st.selectbox(
                "Select a Product",
                options=list(product_options.keys()),
                format_func=lambda x: product_options[x],
                index=selected_index,
                key="product_selector",
                on_change=load_product_data
            )
            
            if st.session_state.selected_product_data:
                product = st.session_state.selected_product_data
                st.success(f"Selected: {product['product_name']}")
                
                with st.expander("Product Details"):
                    st.json(product)
        else:
            st.warning("No products available in the database")

        left_col, right_col = st.columns([1, 2])

        with left_col:
            default_design_name = ""
            default_marketplace_title = ""
            default_design_sku = ""
            default_sizes = []
            default_colors = []
            
            if st.session_state.selected_product_data:
                product = st.session_state.selected_product_data
                default_design_name = product['product_name']
                default_marketplace_title = product['marketplace_title'] or ""
                default_design_sku = product['item_sku'] or ""
                
                if hasattr(st.session_state, 'parsed_sizes'):
                    default_sizes = get_valid_sizes_from_parsed(st.session_state.parsed_sizes)
                
                if hasattr(st.session_state, 'parsed_colors'):
                    default_colors = get_valid_colors_from_parsed(st.session_state.parsed_colors)
                    
                    if not default_colors and st.session_state.parsed_colors:
                        st.info("Colors from product record (hex values):")
                        for hex_color in st.session_state.parsed_colors:
                            if isinstance(hex_color, str) and hex_color.startswith('#'):
                                st.markdown(
                                    f"<div style='display:flex;align-items:center;'>"
                                    f"<div style='width:20px;height:20px;background-color:{hex_color};margin-right:10px;border:1px solid #ccc;'></div>"
                                    f"<span>{hex_color}</span>"
                                    f"</div>",
                                    unsafe_allow_html=True
                                )
            
            design_name = st.text_input("Design Name", placeholder="Value", 
                                        key="design_name", on_change=update_design_sku)
            
            marketplace_title = st.text_input("Marketplace Title (80 character limit)", 
                                             value=default_marketplace_title, 
                                             placeholder="Value", 
                                             key="marketplace_title",
                                             on_change=update_design_sku)
            
            if marketplace_title:
                char_count = len(marketplace_title)
                st.caption(f"{char_count}/80 characters")
                if char_count > 80:
                    st.warning("Marketplace title exceeds 80 character limit")
            
            if not default_design_sku and default_design_name:
                default_design_sku = generate_product_sku(
                    parent_sku=default_design_sku,
                    size=default_sizes[0] if default_sizes else None,
                    color=default_colors[0] if default_colors else None,
                    is_display=True
                )
                st.session_state.design_sku = default_design_sku
            elif not 'design_sku' in st.session_state or not st.session_state.design_sku:
                st.session_state.design_sku = default_design_sku
            
            design_sku = st.text_input("Design SKU", value=st.session_state.design_sku, disabled=True, 
                                       key="design_sku_display")

            sizes = st.multiselect("Select Sizes", AVAILABLE_SIZES, default=default_sizes, 
                                   key="selected_sizes", on_change=update_design_sku)
            
            colors = st.multiselect("Select Colours", AVAILABLE_COLORS, default=default_colors, 
                                    key="selected_colors", on_change=update_design_sku)

            if colors:
                st.write("Selected Colors:")
                color_cols = st.columns(min(4, len(colors)))
                for i, color in enumerate(colors):
                    hex_value = color_name_to_hex(color)
                    with color_cols[i % len(color_cols)]:
                        st.markdown(
                            f"<div style='text-align:center;'>"
                            f"<div style='width:30px;height:30px;background-color:{hex_value};margin:0 auto 5px;border:1px solid #ccc;border-radius:4px;'></div>"
                            f"<div style='font-size:0.8em;'>{color}<br>{hex_value}</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

            design_image = st.file_uploader("Design Image", type=["png", "jpg", "jpeg"], 
                                            key="design_image", on_change=on_file_upload)
            
            if design_image is None and st.session_state.design_image_data is not None:
                design_image = st.session_state.design_image_data

            if st.session_state.selected_product_data and st.session_state.selected_product_data.get('mockup_id'):
                st.info(f"Using Mockup ID: {st.session_state.selected_product_data['mockup_id']}")
            
            if st.session_state.selected_product_data and st.session_state.selected_product_data.get('smart_object_uuid'):
                st.info(f"Using Smart Object UUID: {st.session_state.selected_product_data['smart_object_uuid']}")
            
            if st.button("Generate All Mockups"):
                validation_passed = True
                
                if not design_name or design_name.strip() == "":
                    st.error("Please enter a Design Name.")
                    validation_passed = False
                
                if not marketplace_title or marketplace_title.strip() == "":
                    st.error("Please enter a Marketplace Title.")
                    validation_passed = False
                elif len(marketplace_title) > 80:
                    st.error("Marketplace Title must be 80 characters or less.")
                    validation_passed = False
                
                if not design_image:
                    st.error("Please upload a Design Image to generate mockups.")
                    validation_passed = False
                
                if validation_passed:
                    if not colors:
                        st.warning("No colors selected. Using default color (Red).")
                        selected_colors = ["Red"]
                    else:
                        selected_colors = colors
                    
                    if not hasattr(st.session_state, 'mockup_ids') or not st.session_state.mockup_ids:
                        st.error("No mockup templates available. Please select a product with mockup templates.")
                    else:
                        with st.spinner("Uploading image to S3..."):
                            image_url = upload_image_file_to_s3(design_image, folder="original")
                            
                            if not image_url:
                                st.error("Failed to upload image to S3. Please check your AWS configuration.")
                            else:
                                st.session_state.uploaded_image_url = image_url
                                st.session_state.original_design_url = image_url
                                
                                st.success("✅ Image uploaded to S3")
                        
                                with st.spinner("Generating mockups for all templates..."):
                                    color_hex_list = [color_name_to_hex(color) for color in selected_colors]
                                    
                                    all_mockup_results = generate_all_mockups(image_url, color_hex_list)
                                    
                                    if all_mockup_results:
                                        st.session_state.mockup_results_all = all_mockup_results
                                        
                                        if all_mockup_results and 'results' in all_mockup_results[0]:
                                            mockup_dict = {mockup['color']: mockup['rendered_image_url'] 
                                                           for mockup in all_mockup_results[0]['results']}
                                            st.session_state.mockup_results = mockup_dict
                                        
                                        current_sku = update_design_sku()
                                        
                                        st.session_state.product_data_to_save = {
                                            "design_name": design_name,
                                            "marketplace_title": marketplace_title,
                                            "design_sku": current_sku,
                                            "sizes": sizes,
                                            "colors": colors,
                                            "original_design_url": image_url,
                                            "all_mockup_results": all_mockup_results
                                        }
                                        
                                        total_mockups = sum(len(result['results']) for result in all_mockup_results)
                                        st.success(f"✅ Generated {total_mockups} mockups for {len(all_mockup_results)} templates successfully!")
                                    else:
                                        st.error("Failed to generate any mockups. See error details above.")
                                        st.session_state.mockup_results = None
            
            if hasattr(st.session_state, 'mockup_results_all') and st.session_state.mockup_results_all and hasattr(st.session_state, 'product_data_to_save'):
                if st.button("Save All Mockups to Database", key="save_all_mockups_button"):
                    with st.spinner("Saving all mockups to S3 and database..."):
                        import tempfile
                        import os
                        import boto3
                        from botocore.exceptions import ClientError
                        
                        s3_client = boto3.client('s3', 
                            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                            region_name=os.environ.get('AWS_REGION', 'us-east-1')
                        )
                        bucket_name = os.environ.get('AWS_BUCKET_NAME', 'streamlet')
                        region = os.environ.get('AWS_REGION', 'us-east-1')
                        
                        all_mockup_s3_urls = {}
                        all_mockup_results = st.session_state.product_data_to_save["all_mockup_results"]
                        product_data = st.session_state.product_data_to_save
                        sizes = product_data["sizes"]
                        colors = product_data["colors"]
                        color_hex_set = {color_name_to_hex(color) for color in colors}
                        
                        total_iterations = sum(len([m for m in mockup_set['results'] if m['color'] in color_hex_set]) for mockup_set in all_mockup_results)
                        progress_bar = st.progress(0)
                        completed = 0
                        
                        temp_dir = tempfile.mkdtemp()
                        
                        st.session_state.used_sku_numbers = set()
                        st.session_state.sku_sequence_number = None
                        
                        color_to_mockup_urls = {}
                        
                        for mockup_set_idx, mockup_set in enumerate(all_mockup_results):
                            mockup_id = mockup_set['mockup_id']
                            
                            filtered_results = [m for m in mockup_set['results'] if m['color'] in color_hex_set]
                            
                            for mockup in filtered_results:
                                hex_color = mockup['color']
                                mockup_url = mockup['rendered_image_url']
                                
                                if hex_color not in color_to_mockup_urls:
                                    color_to_mockup_urls[hex_color] = {}
                                
                                try:
                                    response = requests.get(mockup_url, timeout=15)
                                    if response.status_code == 200:
                                        color_name = hex_to_color_name(hex_color.lstrip('#'))
                                        temp_sku = generate_product_sku(
                                            parent_sku=st.session_state.selected_product_data['item_sku'] if st.session_state.selected_product_data and 'item_sku' in st.session_state.selected_product_data else None,
                                            size=sizes[0] if sizes else None,
                                            color=color_name
                                        )
                                        item_sku = st.session_state.selected_product_data['item_sku'] if st.session_state.selected_product_data and 'item_sku' in st.session_state.selected_product_data else "unknown"
                                        local_filename = f"mockup_{item_sku}_{color_name}_{mockup_id[-6:]}.png"
                                        local_filepath = os.path.join(temp_dir, local_filename)
                                        
                                        with open(local_filepath, 'wb') as f:
                                            f.write(response.content)
                                        
                                        s3_key = f"mockups/{local_filename}"
                                        try:
                                            s3_client.upload_file(
                                                local_filepath,
                                                bucket_name,
                                                s3_key,
                                                ExtraArgs={
                                                    'ContentType': 'image/png',
                                                    'StorageClass': 'STANDARD',
                                                },
                                                Config=boto3.s3.transfer.TransferConfig(
                                                    use_threads=True,
                                                    max_concurrency=10,
                                                    multipart_threshold=8388608,
                                                    multipart_chunksize=8388608,
                                                )
                                            )
                                            
                                            s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
                                            color_to_mockup_urls[hex_color][mockup_id] = s3_url
                                        except Exception as e:
                                            st.warning(f"Error uploading to S3: {e}")
                                        
                                        try:
                                            os.unlink(local_filepath)
                                        except Exception:
                                            pass
                                    else:
                                        st.warning(f"Failed to download mockup (Status: {response.status_code})")
                                    
                                except Exception as e:
                                    st.warning(f"Error processing mockup: {e}")
                                
                                completed += 1
                                progress_bar.progress(min(completed / total_iterations, 1.0))
                        
                        import shutil
                        try:
                            shutil.rmtree(temp_dir)
                        except Exception:
                            pass
                        
                        parent_sku = ""
                        if st.session_state.selected_product_id:
                            parent_product = db.get_product(st.session_state.selected_product_id)
                            if parent_product and 'item_sku' in parent_product:
                                parent_sku = parent_product['item_sku']
                        
                        success_count = 0
                        
                        st.session_state.used_sku_numbers = set()
                        st.session_state.sku_sequence_number = None
                        
                        product_variants = {}
                        for hex_color, mockup_urls_by_id in color_to_mockup_urls.items():
                            color_name = hex_to_color_name(hex_color.lstrip('#'))
                            if not color_name:
                                continue
                            
                            for size in sizes:
                                variant_key = (size, color_name)
                                if variant_key not in product_variants:
                                    product_variants[variant_key] = {
                                        'size': size,
                                        'color': color_name,
                                        'mockup_urls': [],
                                        'mockup_ids': [],
                                        'smart_object_uuids': [],
                                        'mockup_url_dict': {}
                                    }
                                
                                for mockup_id, url in mockup_urls_by_id.items():
                                    if mockup_id not in product_variants[variant_key]['mockup_ids']:
                                        product_variants[variant_key]['mockup_ids'].append(mockup_id)
                                        product_variants[variant_key]['mockup_urls'].append(url)
                                        
                                        for mockup_set in all_mockup_results:
                                            if mockup_set['mockup_id'] == mockup_id:
                                                smart_object_uuid = mockup_set.get('smart_object_uuid')
                                                product_variants[variant_key]['smart_object_uuids'].append(smart_object_uuid)
                                                break
                                        
                                product_variants[variant_key]['mockup_url_dict'][hex_color] = mockup_urls_by_id
                        
                        for variant_key, variant_data in product_variants.items():
                            size, color = variant_key
                            try:
                                current_design_sku = generate_product_sku(
                                    parent_sku=parent_sku,
                                    size=size,
                                    color=color
                                )
                                
                                mockup_urls_json = {}
                                hex_color = color_name_to_hex(color)
                                if hex_color in color_to_mockup_urls:
                                    mockup_urls_json[hex_color] = ", ".join(color_to_mockup_urls[hex_color].values())
                                
                                product_dict = {
                                    "product_name": f"{product_data['design_name']}",
                                    "marketplace_title": product_data["marketplace_title"],
                                    "item_sku": current_design_sku,
                                    "parent_sku": parent_sku,
                                    "size": json.dumps([size]),
                                    "color": json.dumps([hex_color]),
                                    "original_design_url": product_data["original_design_url"],
                                    "mockup_urls": json.dumps(mockup_urls_json),
                                    "mockup_ids": json.dumps(variant_data['mockup_ids']),
                                    "smart_object_uuids": json.dumps(variant_data['smart_object_uuids'])
                                }
                                
                                if st.session_state.selected_product_id:
                                    product_dict["parent_product_id"] = st.session_state.selected_product_id
                                
                                new_id = db.create_generated_product(product_dict)
                                if new_id:
                                    success_count += 1
                            except Exception as e:
                                st.error(f"Error saving variant {size}/{color}: {str(e)}")
                        
                        if success_count > 0:
                            st.success(f"Successfully saved {success_count} product variants to database!")
                            st.session_state.product_data_to_save = None
                            
                            if st.button("Go to Product List to view your new products"):
                                st.experimental_set_query_params(page="product_list")
                                st.rerun()
                        else:
                            st.error("Failed to save any products to database. Check the errors above.")

        with right_col:
            st.write("### Preview by Colour")
            
            if hasattr(st.session_state, 'mockup_results_all') and st.session_state.mockup_results_all:
                all_templates = st.session_state.mockup_results_all
                
                if st.session_state.template_generate_mockup is not None and st.session_state.template_generate_color is not None:
                    template_idx = st.session_state.template_generate_mockup
                    color_name = st.session_state.template_generate_color
                    
                    generate_template_mockup_on_demand(template_idx, color_name)
                    
                    st.session_state.template_generate_mockup = None
                    st.session_state.template_generate_color = None
                    st.rerun()
                
                for template_idx, template in enumerate(all_templates):
                    st.write(f"## Template {template_idx + 1}")
                    mockup_id = template['mockup_id']
                    results = template.get('results', [])
                    
                    if not results:
                        st.warning(f"No mockups generated yet for Template {template_idx + 1}")
                        continue

                    color_to_url_map = {}
                    generated_color_names = []
                    
                    for result in results:
                        hex_color = result['color']
                        color_name = hex_to_color_name(hex_color.lstrip('#'))
                        if color_name:
                            color_to_url_map[hex_color] = result['rendered_image_url']
                            generated_color_names.append(color_name)
                    
                    if not generated_color_names:
                        st.warning(f"No recognized colors in the generated mockups for Template {template_idx + 1}")
                        continue
                    
                    num_colors = len(generated_color_names)
                    cols = st.columns(num_colors)
                    
                    for i, col in enumerate(cols):
                        if i < len(generated_color_names):
                            color_name = generated_color_names[i]
                            hex_color = color_name_to_hex(color_name)
                            
                            with col:
                                selected_color = st.selectbox(
                                    f"Mockup {i+1} Color",
                                    AVAILABLE_COLORS,
                                    index=AVAILABLE_COLORS.index(color_name),
                                    key=f"template_{template_idx}_color_{i}",
                                    on_change=on_template_color_change,
                                    args=(template_idx, i)
                                )
                                
                                selected_hex = color_name_to_hex(selected_color)
                                
                                st.markdown(
                                    f"<div style='background-color:{selected_hex};width:30px;height:30px;border-radius:5px;margin:10px 0;border:1px solid #ccc;'></div>", 
                                    unsafe_allow_html=True
                                )
                                
                                if selected_color != color_name:
                                    new_hex = color_name_to_hex(selected_color)
                                    mockup_exists = False
                                    
                                    for result in results:
                                        if result['color'] == new_hex:
                                            st.image(
                                                result['rendered_image_url'],
                                                caption=f"{selected_color}",
                                                use_container_width=True
                                            )
                                            mockup_exists = True
                                            break
                                    
                                    if not mockup_exists:
                                        st.warning(f"No mockup for {selected_color} yet")
                                        is_generating = (st.session_state.get('template_generate_mockup') == template_idx and 
                                                        st.session_state.get('template_generate_color') == selected_color and
                                                        st.session_state.get('template_color_index') == i)
                                        
                                        if is_generating:
                                            with st.spinner(f"Generating {selected_color} mockup..."):
                                                st.markdown("⏳ Generating mockup...")
                                        else:
                                            if st.button(f"Generate {selected_color}", key=f"gen_{template_idx}_{i}"):
                                                st.session_state.template_generate_mockup = template_idx
                                                st.session_state.template_generate_color = selected_color
                                                st.rerun()
                                else:
                                    st.image(
                                        color_to_url_map[hex_color],
                                        caption=f"{color_name}",
                                        use_container_width=True
                                    )
            
            elif st.session_state.mockup_results:
                available_mockup_colors = list(st.session_state.mockup_results.keys())
                generated_color_names = []
                hex_to_name_mapping = {}
                
                for hex_color in available_mockup_colors:
                    color_name = hex_to_color_name(hex_color.lstrip('#'))
                    if color_name:
                        generated_color_names.append(color_name)
                        hex_to_name_mapping[hex_color] = color_name
                
                if not st.session_state.panel_color_mapping:
                    for i, hex_color in enumerate(available_mockup_colors):
                        if i not in st.session_state.panel_color_mapping:
                            st.session_state.panel_color_mapping[i] = hex_color
                
                if st.session_state.generate_for_panel is not None and st.session_state.generate_color is not None:
                    panel_idx = st.session_state.generate_for_panel
                    color_name = st.session_state.generate_color
                    hex_selected = color_name_to_hex(color_name)
                    
                    with st.spinner(f"Generating mockup for {color_name}..."):
                        if generate_on_demand_mockup(color_name):
                            st.session_state.panel_color_mapping[panel_idx] = hex_selected
                        
                        st.session_state.generate_for_panel = None
                        st.session_state.generate_color = None
                        st.rerun()
                
                num_mockups = len(available_mockup_colors)
                cols = st.columns(num_mockups)
                
                for i, col in enumerate(cols):
                    if i < len(available_mockup_colors):
                        hex_color = available_mockup_colors[i]
                        color_name = hex_to_name_mapping.get(hex_color, "Unknown")
                        
                        with col:
                            preview_key = f"preview_{i}_color"
                            
                            if i not in st.session_state.mockup_panel_colors:
                                st.session_state.mockup_panel_colors[i] = color_name
                            
                            current_color = st.session_state.mockup_panel_colors.get(i, color_name)
                            selected_color = st.selectbox(
                                f"Mockup {i+1}",
                                AVAILABLE_COLORS,
                                index=AVAILABLE_COLORS.index(current_color) if current_color in AVAILABLE_COLORS else 0,
                                key=preview_key,
                                on_change=on_mockup_color_change,
                                args=(i,)
                            )
                            
                            selected_hex = color_name_to_hex(selected_color)
                            
                            st.markdown(
                                f"<div style='background-color:{selected_hex};width:30px;height:30px;border-radius:5px;margin:10px 0;border:1px solid #ccc;'></div>", 
                                unsafe_allow_html=True
                            )
                            
                            current_hex = st.session_state.panel_color_mapping.get(i, hex_color)
                            
                            if selected_hex in st.session_state.mockup_results:
                                st.image(
                                    st.session_state.mockup_results[selected_hex],
                                    caption=f"{selected_color}",
                                    use_container_width=True
                                )
                            else:
                                st.warning(f"No mockup for {selected_color} yet")
                                if st.button(f"Generate {selected_color}", key=f"gen_mock_{i}"):
                                    st.session_state.generate_for_panel = i
                                    st.session_state.generate_color = selected_color
                                    st.rerun()
                                
            else:
                st.info("Generate mockups to see previews here")
                
                available_colors = colors if colors else AVAILABLE_COLORS
                
                num_preview_cols = min(len(available_colors), 5) if available_colors else 3
                preview_cols = st.columns(num_preview_cols)
                
                for i, col in enumerate(preview_cols):
                    with col:
                        preview_key = f"preview{i+1}_color"
                        
                        if i < len(available_colors):
                            default_index = 0
                            color_option = st.selectbox(
                                f"Select Color {i+1}", 
                                available_colors,
                                index=i,
                                key=preview_key
                            )
                            
                            if design_image:
                                st.image(design_image, width=150, caption=f"{color_option} (Preview Only)")
                                if st.session_state.uploaded_image_url:
                                    if st.button(f"Generate {color_option}", key=f"gen_mockup{i+1}"):
                                        if generate_on_demand_mockup(color_option):
                                            st.rerun()
                            else:
                                st.image("https://via.placeholder.com/150", width=150, caption=color_option)

    generate_product_page()

def upload_to_s3(local_path, s3_key):
    try:
        import boto3
        from botocore.exceptions import ClientError
        import os
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
        
        bucket_name = os.environ.get('S3_BUCKET_NAME', 'streamlet')
        region = os.environ.get('AWS_REGION', 'us-east-1')
        
        s3_client.upload_file(
            local_path,
            bucket_name,
            s3_key,
            ExtraArgs={
                'ContentType': 'image/png',
            }
        )
        
        s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
        return s3_url
    except Exception as e:
        st.error(f"Error uploading to S3: {e}")
        return None
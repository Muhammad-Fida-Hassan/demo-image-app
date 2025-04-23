import streamlit as st
import json
import random
import string
from utils.database import get_database_connection
from utils.dynamic_mockups import get_mockups
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

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

    # Check if we need to reset the form (after successful submission)
    if 'reset_form' in st.session_state and st.session_state.reset_form:
        # Clear the reset flag
        st.session_state.reset_form = False
        
        # Clear session state for the form fields
        if 'mockup_selection' in st.session_state:
            st.session_state.mockup_selection = ""
        if 'item_name' in st.session_state:
            st.session_state.item_name = ""
        if 'mockup_id' in st.session_state:
            st.session_state.mockup_id = ""
        if 'preview_mockup_selection' in st.session_state:
            st.session_state.preview_mockup_selection = ""
        if 'sku_prefix' in st.session_state:
            st.session_state.sku_prefix = ""
        if 'price' in st.session_state:
            st.session_state.price = 0.0
        if 'quantity' in st.session_state:
            st.session_state.quantity = 0
        if 'tax_class' in st.session_state:
            st.session_state.tax_class = ""

    # Initialize session state for sizes, colors, and other fields
    if 'sizes' not in st.session_state:
        st.session_state.sizes = []
    if 'colors' not in st.session_state:
        st.session_state.colors = []
    if 'mockup_id' not in st.session_state:
        st.session_state.mockup_id = ""
    if 'mockup_selection' not in st.session_state:
        st.session_state.mockup_selection = ""
    if 'item_name' not in st.session_state:
        st.session_state.item_name = ""
    if 'preview_mockup_selection' not in st.session_state:
        st.session_state.preview_mockup_selection = ""
    if 'available_sizes' not in st.session_state:
        st.session_state.available_sizes = ["Small", "Medium", "Large", "X-Large", "XX-Large", "XXX-Large"]
    if 'selected_sizes' not in st.session_state:
        st.session_state.selected_sizes = []
    if 'sku_prefix' not in st.session_state:
        st.session_state.sku_prefix = ""
    if 'price' not in st.session_state:
        st.session_state.price = 0.0
    if 'quantity' not in st.session_state:
        st.session_state.quantity = 0
    if 'tax_class' not in st.session_state:
        st.session_state.tax_class = ""

    # Initialize session state for mockup selections
    if 'mockup_selections' not in st.session_state:
        st.session_state.mockup_selections = []
    if 'mockup_ids' not in st.session_state:
        st.session_state.mockup_ids = []

    # Color to hex mapping
    COLOR_HEX_MAP = {
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

    # Function to generate product SKU based on name, colors, and sizes
    def generate_product_sku(item_name, colors=None, sizes=None):
        """Generate a SKU based on item name, colors, and sizes"""
        if not item_name:
            return ""
            
        # Remove spaces and convert to uppercase
        clean_name = item_name.replace(" ", "").upper()
        
        # Take the first 3 characters of the name, or fewer if the name is shorter
        name_part = clean_name[:min(3, len(clean_name))]
        
        # Add a dash after the name part
        sku = name_part + "-"
        
        # Add 3 random numbers
        random_numbers = ''.join(random.choice(string.digits) for _ in range(3))
        sku += random_numbers
        
        return sku

    # Function to validate SKU prefix
    def validate_sku_prefix(prefix):
        """Validate that the SKU prefix is exactly 4 characters long and contains only letters"""
        if not prefix:
            return False
        if len(prefix) != 4:
            return False
        return prefix.isalpha()

    # Function to generate final SKU based on prefix and product count
    def generate_final_sku(prefix):
        """Generate a SKU with format PREFIX-XXXX where XXXX is the product count padded to 4 digits"""
        db = get_database_connection()
        try:
            product_count = db.get_product_count()  # Get current product count
            product_count += 1  # Increment for the new product
            padded_count = f"{product_count:04d}"  # Pad to 4 digits
            return f"{prefix.upper()}-{padded_count}"
        except Exception as e:
            st.error(f"Error generating SKU: {e}")
            return None

    # Function to update SKU based on current item name, colors, and sizes
    def update_sku():
        try:
            st.session_state.sku = generate_product_sku(
                st.session_state.item_name, 
                st.session_state.colors, 
                st.session_state.sizes
            )
        except Exception as e:
            print(f"Couldn't update SKU: {e}")
            if 'pending_sku_update' not in st.session_state:
                st.session_state.pending_sku_update = True

    # Function to generate random SKU
    def generate_random_sku(prefix="", length=8):
        """Generate a random SKU with specified length using letters and digits"""
        chars = string.ascii_uppercase + string.digits
        random_part = ''.join(random.choice(chars) for _ in range(length))
        return f"{prefix}{random_part}" if prefix else random_part

    # Function to add multiple sizes
    def add_sizes():
        st.session_state.sizes = []
        for size in st.session_state.selected_sizes:
            size_sku = generate_random_sku(prefix=f"{size.lower()[:1]}-", length=6)
            st.session_state.sizes.append({
                'name': size,
                'sku': size_sku
            })
        update_sku()

    # Function to add multiple colors
    def add_colors():
        st.session_state.colors = []
        for color in st.session_state.selected_colors:
            st.session_state.colors.append(COLOR_HEX_MAP.get(color, "#FFFFFF"))
        update_sku()

    # Function to update item name and mockup ID when selection changes
    def update_mockup_selection():
        """Update mockup IDs and related data when selection changes"""
        if "preview_mockup_selection" in st.session_state:
            st.session_state.mockup_selections = st.session_state.preview_mockup_selection
            
            st.session_state.mockup_ids = []
            for mockup in st.session_state.mockup_selections:
                if mockup and mockup != "":
                    st.session_state.mockup_ids.append(mockup_id_map.get(mockup, ""))
            
            if st.session_state.mockup_selections:
                st.session_state.mockup_selection = st.session_state.mockup_selections[0]
                st.session_state.item_name = st.session_state.mockup_selection.split(",")[0] if "," in st.session_state.mockup_selection else st.session_state.mockup_selection
                update_sku()
            else:
                st.session_state.mockup_selection = ""
                st.session_state.item_name = ""
                st.session_state.mockup_id = ""

    # Function to update item name and SKU
    def update_item_name():
        if "form_item_name" in st.session_state:
            st.session_state.item_name = st.session_state.form_item_name
            update_sku()

    # Fetch mockups from API
    mockups = get_mockups()
    print(f"Mockups fetched: {mockups}")

    # Create descriptive options for the mockup selection
    mockup_options = [""]
    mockup_id_map = {}

    for mockup in mockups:
        print(f"Processing mockup: {mockup}")
        mockup_name = mockup.get('name', 'Unnamed Mockup')
        smart_objects_info = []
        for so in mockup.get('smart_objects', []):
            if 'Background' not in so.get('name', ''):
                so_name = so.get('name', 'Unnamed')
                option_text = f"{so_name} - {mockup_name}"
                smart_objects_info.append(option_text)
                mockup_options.append(option_text)
                
                mockup_id = mockup.get('id', mockup.get('uuid', ''))
                print(f"Mapping '{option_text}' to ID: {mockup_id}")
                mockup_id_map[option_text] = mockup_id
        
        if not smart_objects_info and 'Background' not in mockup_name:
            option_text = f"No printable objects - {mockup_name}"
            mockup_options.append(option_text)
            mockup_id = mockup.get('id', mockup.get('uuid', ''))
            mockup_id_map[option_text] = mockup_id

    # Create a function to handle mockup selection outside the form
    def handle_mockup_selection():
        selection_container = st.container()
        
        with selection_container:
            if 'mockup_selections' in st.session_state:
                if not isinstance(st.session_state.mockup_selections, list):
                    if isinstance(st.session_state.mockup_selections, str):
                        st.session_state.mockup_selections = [st.session_state.mockup_selections] if st.session_state.mockup_selections else []
                    else:
                        try:
                            st.session_state.mockup_selections = list(st.session_state.mockup_selections)
                        except:
                            st.session_state.mockup_selections = []
            
            if 'preview_mockup_selection' in st.session_state:
                if isinstance(st.session_state.preview_mockup_selection, list):
                    st.session_state.preview_mockup_selection = [
                        option for option in st.session_state.preview_mockup_selection 
                        if option in mockup_options
                    ]
                else:
                    st.session_state.preview_mockup_selection = []
            else:
                st.session_state.preview_mockup_selection = []
            
            st.multiselect(
                "Select Mockups (Choose multiple)",
                options=mockup_options,
                key="preview_mockup_selection",
                on_change=update_mockup_selection
            )

    # Page configuration
    st.title("Add Blank Item")

    # Display the mockup selection outside the form
    handle_mockup_selection()

    # Form for adding a blank item
    with st.form(key="add_blank_item_form", clear_on_submit=False):
        # Item Name and SKU
        st.subheader("Item Name")
        st.text_input("Item Name", placeholder="Enter item name", value=st.session_state.item_name, key="form_item_name")
        
        if "form_item_name" in st.session_state:
            st.session_state.item_name = st.session_state.form_item_name
        
        st.subheader("SKU Prefix")
        st.text_input(
            "SKU Prefix (Exactly 4 letters)",
            placeholder="Enter exactly 4 letter prefix (e.g., MOCK)",
            key="sku_prefix",
            value=st.session_state.sku_prefix,
            help="Enter exactly 4 letters for the SKU prefix. The final SKU will be in the format PREFIX-XXXX."
        )

        # Size Section
        st.subheader("Size")
        st.multiselect(
            "Select Sizes", 
            options=st.session_state.available_sizes,
            default=st.session_state.selected_sizes,
            key="selected_sizes"
        )
        
        size_button = st.form_submit_button("Add Sizes", on_click=add_sizes)

        if st.session_state.sizes:
            st.text_area("Size SKUs", value="\n".join([f"{size['name']} - {size['sku']}" for size in st.session_state.sizes]), height=100)

        # Price and Quantity Section
        st.subheader("Price and Quantity")
        st.number_input("Price", min_value=0.0, step=0.01, value=st.session_state.price, key="form_price")
        st.number_input("Quantity", min_value=0, step=1, value=st.session_state.quantity, key="form_quantity")

        # Tax Class Section
        st.subheader("Tax Class")
        st.selectbox(
            "Select Tax Class",
            options=["VAT Standard", "VAT Exempt"],
            index=0 if st.session_state.tax_class == "VAT Standard" else 1 if st.session_state.tax_class == "VAT Exempt" else 0,
            key="form_tax_class"
        )

        # Color Section
        st.subheader("Color")
        st.multiselect(
            "Select Colors",
            options=list(COLOR_HEX_MAP.keys()),
            key="selected_colors"
        )
        
        if "selected_colors" in st.session_state and st.session_state.selected_colors:
            st.write("Color Preview:")
            cols = st.columns(len(st.session_state.selected_colors))
            for i, color in enumerate(st.session_state.selected_colors):
                hex_color = COLOR_HEX_MAP.get(color, "#FFFFFF")
                with cols[i]:
                    st.markdown(f"""
                        <div style="
                            background-color: {hex_color}; 
                            width: 30px; 
                            height: 30px; 
                            border-radius: 5px;
                            border: 1px solid #ddd;
                        "></div>
                        <p>{color}<br>{hex_color}</p>
                    """, unsafe_allow_html=True)
        
        color_button = st.form_submit_button("Add Colors", on_click=add_colors)

        if st.session_state.colors:
            st.text_area("Selected Colors", value="\n".join(st.session_state.colors), height=100)

        # Mockup ID display
        st.subheader("Selected Mockups")
        if st.session_state.mockup_selections:
            for i, mockup in enumerate(st.session_state.mockup_selections):
                mockup_id = mockup_id_map.get(mockup, "")
                st.text_input(
                    f"Mockup {i+1}: {mockup}",
                    value=mockup_id,
                    key=f"mockup_id_display_{i}",
                    disabled=True
                )
        else:
            st.info("No mockups selected.")
    
        # Submit button
        submit_button = st.form_submit_button(label="Save")

    # After form submission, handle updates
    if "form_item_name" in st.session_state and st.session_state.form_item_name != st.session_state.item_name:
        st.session_state.item_name = st.session_state.form_item_name
        update_sku()

    # Update price, quantity, and tax class
    if "form_price" in st.session_state:
        st.session_state.price = st.session_state.form_price
    if "form_quantity" in st.session_state:
        st.session_state.quantity = st.session_state.form_quantity
    if "form_tax_class" in st.session_state:
        st.session_state.tax_class = st.session_state.form_tax_class

    # Update mockup selection
    if st.session_state.mockup_selection and st.session_state.mockup_selection != "":
        current_mockup_id = mockup_id_map.get(st.session_state.mockup_selection, "")
        if current_mockup_id != st.session_state.mockup_id:
            try:
                st.session_state.mockup_id = current_mockup_id
                st.session_state.item_name = (st.session_state.mockup_selection.split(",")[0] 
                                          if "," in st.session_state.mockup_selection 
                                          else st.session_state.mockup_selection)
                update_sku()
            except Exception as e:
                print(f"Error updating mockup selection: {e}")
                if 'pending_sku_update' not in st.session_state:
                    st.session_state.pending_sku_update = True

    # Check for pending SKU update
    if 'pending_sku_update' in st.session_state and st.session_state.pending_sku_update:
        try:
            st.session_state.sku = generate_product_sku(
                st.session_state.item_name,
                st.session_state.colors,
                st.session_state.sizes
            )
            st.session_state.pending_sku_update = False
        except Exception as e:
            print(f"Still couldn't update SKU: {e}")

    # Process form submission
    if submit_button:
        st.session_state.item_name = st.session_state.form_item_name if "form_item_name" in st.session_state else st.session_state.item_name
        sku_prefix = st.session_state.sku_prefix
        
        # Validate SKU prefix
        if not validate_sku_prefix(sku_prefix):
            st.error("Please enter a valid SKU prefix (exactly 4 letters only).")
        else:
            # Generate final SKU
            item_sku = generate_final_sku(sku_prefix)
            if not item_sku:
                st.error("Failed to generate SKU. Please try again.")
            else:
                selected_mockup_ids = []
                smart_object_uuids = []
                
                for mockup_selection in st.session_state.mockup_selections:
                    selected_mockup_id = mockup_id_map.get(mockup_selection, "")
                    if " - " in mockup_selection:
                        selected_mockup_name = mockup_selection.split(" - ")[0]
                    else:
                        selected_mockup_name = mockup_selection.split(",")[0] if "," in mockup_selection else mockup_selection
                    
                    for mockup in mockups:
                        mockup_id = mockup.get('id', mockup.get('uuid', ''))
                        if mockup_id == selected_mockup_id:
                            for so in mockup.get('smart_objects', []):
                                if 'Background' not in so.get('name', '') and so.get('name', '') == selected_mockup_name:
                                    smart_object_uuids.append(so.get('uuid', None))
                                    break
                            break
                    
                    selected_mockup_ids.append(selected_mockup_id)
                
                mockup_ids_json = json.dumps(selected_mockup_ids)
                smart_object_uuids_json = json.dumps(smart_object_uuids)
                
                # Prepare product data with new fields
                product_data = {
                    'product_name': st.session_state.item_name,
                    'item_sku': item_sku,
                    'parent_child': 'Parent',
                    'parent_sku': None,
                    'size': st.session_state.size_name if not st.session_state.sizes else json.dumps(st.session_state.sizes),
                    'color': st.session_state.color_name if not st.session_state.colors else json.dumps(st.session_state.colors),
                    'mockup_id': selected_mockup_ids[0] if selected_mockup_ids else None,
                    'mockup_ids': mockup_ids_json,
                    'image_url': None,
                    'marketplace_title': None,
                    'category': ", ".join(st.session_state.mockup_selections),
                    'tax_class': st.session_state.tax_class,
                    'quantity': st.session_state.quantity,
                    'price': st.session_state.price,
                    'smart_object_uuid': smart_object_uuids[0] if smart_object_uuids else None,
                    'smart_object_uuids': smart_object_uuids_json,
                }

                # Validate required fields
                if not product_data['product_name'] or not product_data['item_sku']:
                    st.error("Please fill in the Item Name and SKU fields.")
                elif not product_data['mockup_id']:
                    st.error("Please select a mockup.")
                else:
                    print(f"Product data before saving: {product_data}")
                    st.write("Product Data to be saved:", product_data)

                    db = get_database_connection()
                    try:
                        product_id = db.add_product(product_data)
                        if product_id:
                            st.success(f"Product added successfully with ID: {product_id}")
                            
                            st.session_state.reset_form = True
                            
                            st.session_state.sizes = []
                            st.session_state.colors = []
                            
                            st.rerun()
                        else:
                            st.error("Failed to add product. Database returned no product ID.")
                    except Exception as e:
                        st.error(f"An error occurred while saving the product: {e}")
                        st.write("Debug Info:", product_data)
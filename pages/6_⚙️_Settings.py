import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from utils.database import get_database_connection
from utils.ftp_utils import test_ftp_connection
import pandas as pd

# Page configuration
st.set_page_config(
    page_title="Settings",
    page_icon="⚙️",
    layout="wide"
)

# Load configuration for authentication
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
    # Initialize database connection
    db = get_database_connection()
    
    st.title("⚙️ Settings")
    
    # Create tabs for different setting categories
    tab1, tab2 = st.tabs(["FTP Settings", "General Settings"])
    
    with tab1:
        st.header("FTP Server Settings")
        
        st.markdown("""
        Configure FTP server credentials to upload product CSV exports directly to your server.
        These settings will be saved in the database and can be used from the Export page.
        """)
        
        # Initialize session state for FTP form
        if 'ftp_edit_mode' not in st.session_state:
            st.session_state.ftp_edit_mode = False
        if 'ftp_edit_id' not in st.session_state:
            st.session_state.ftp_edit_id = None
        if 'clear_form' not in st.session_state:
            st.session_state.clear_form = False
        
        # Function to toggle edit mode
        def toggle_edit_mode(ftp_id=None):
            st.session_state.ftp_edit_mode = not st.session_state.ftp_edit_mode
            st.session_state.ftp_edit_id = ftp_id
        
        # Get existing FTP settings
        ftp_settings_df = db.get_ftp_settings()
        
        # Display existing FTP settings
        if not ftp_settings_df.empty:
            st.subheader("Saved FTP Servers")
            
            # Format the dataframe for display
            display_df = ftp_settings_df.copy()
            display_df['password'] = '••••••••'  # Mask passwords
            display_df['default'] = display_df['is_default'].apply(lambda x: '✅' if x else '')
            
            # Display only relevant columns
            cols_to_display = ['id', 'host', 'port', 'username', 'default', 'updated_at']
            display_df = display_df[cols_to_display].rename(columns={
                'id': 'ID',
                'host': 'Host',
                'port': 'Port',
                'username': 'Username',
                'default': 'Default',
                'updated_at': 'Last Updated'
            })
            
            st.dataframe(display_df, use_container_width=True)
            
            # Add actions for each FTP setting
            col1, col2, col3 = st.columns(3)
            
            with col1:
                setting_to_edit = st.selectbox(
                    "Select FTP server to edit:",
                    options=[f"{row['host']} ({row['id']})" for _, row in ftp_settings_df.iterrows()],
                    format_func=lambda x: x.split('(')[0].strip()
                )
                
                selected_id = int(setting_to_edit.split('(')[-1].split(')')[0]) if setting_to_edit else None
            
            with col2:
                if st.button("Edit Selected", use_container_width=True):
                    if selected_id:
                        ftp_setting = db.get_ftp_setting(selected_id)
                        if ftp_setting:
                            # Initialize these values for the form to use
                            st.session_state.temp_host = ftp_setting['host']
                            st.session_state.temp_port = ftp_setting['port']
                            st.session_state.temp_username = ftp_setting['username'] 
                            st.session_state.temp_password = ftp_setting['password']
                            st.session_state.temp_is_default = ftp_setting['is_default']
                            st.session_state.ftp_edit_id = selected_id
                            st.session_state.ftp_edit_mode = True
                            st.rerun()
            
            with col3:
                if st.button("Delete Selected", use_container_width=True):
                    if selected_id:
                        # Check if this is the default setting
                        is_default = False
                        for _, row in ftp_settings_df.iterrows():
                            if row['id'] == selected_id and row['is_default']:
                                is_default = True
                                break
                        
                        if is_default and len(ftp_settings_df) > 1:
                            st.warning("You are about to delete the default FTP server. Please set another server as default first.")
                        else:
                            if db.delete_ftp_setting(selected_id):
                                st.success(f"FTP setting with ID {selected_id} deleted")
                                st.rerun()
                            else:
                                st.error(f"Failed to delete FTP setting with ID {selected_id}")
            
            # Add button to set selected as default
            if st.button("Set as Default", use_container_width=True):
                if selected_id:
                    if db.set_ftp_setting_as_default(selected_id):
                        st.success(f"FTP setting with ID {selected_id} set as default")
                        st.rerun()
                    else:
                        st.error(f"Failed to set FTP setting with ID {selected_id} as default")
        
        # Always show the FTP form section
        st.markdown("---")
        st.subheader("Add New FTP Server")
        
        # Initialize temporary values for form to use
        if 'temp_host' not in st.session_state:
            st.session_state.temp_host = ""
        if 'temp_port' not in st.session_state:
            st.session_state.temp_port = 21
        if 'temp_username' not in st.session_state:
            st.session_state.temp_username = ""
        if 'temp_password' not in st.session_state:
            st.session_state.temp_password = ""
        if 'temp_is_default' not in st.session_state:
            st.session_state.temp_is_default = False
        
        # Create a form for FTP settings
        with st.form(key="ftp_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                host = st.text_input("FTP Host", 
                                    value=st.session_state.temp_host, 
                                    placeholder="ftp.example.com",
                                    key="ftp_host")
                
                username = st.text_input("Username", 
                                        value=st.session_state.temp_username,
                                        key="ftp_username")
                
                is_default = st.checkbox("Set as Default", 
                                        value=st.session_state.temp_is_default,
                                        key="ftp_is_default")
                
            with col2:
                port = st.number_input("Port", 
                                    min_value=1, 
                                    max_value=65535, 
                                    value=st.session_state.temp_port,
                                    key="ftp_port")
                
                password = st.text_input("Password", 
                                        type="password",
                                        value=st.session_state.temp_password,
                                        key="ftp_password")
            
            col1, col2 = st.columns(2)
            
            with col1:
                submit_button = st.form_submit_button("Save FTP Server", use_container_width=True)
            
            with col2:
                test_button = st.form_submit_button("Test Connection", use_container_width=True)
            
            if submit_button:
                # Validate form
                if not host:
                    st.error("FTP Host is required")
                elif not username:
                    st.error("Username is required")
                elif not password:
                    st.error("Password is required")
                else:
                    ftp_data = {
                        'host': host,
                        'port': port,
                        'username': username,
                        'password': password,
                        'is_default': is_default
                    }
                    
                    if st.session_state.ftp_edit_id:
                        # Update existing FTP setting
                        if db.update_ftp_setting(st.session_state.ftp_edit_id, ftp_data):
                            st.success(f"FTP server {host} updated")
                            # Reset the form by clearing temp variables
                            st.session_state.temp_host = ""
                            st.session_state.temp_port = 21
                            st.session_state.temp_username = ""
                            st.session_state.temp_password = ""
                            st.session_state.temp_is_default = False
                            st.session_state.ftp_edit_id = None
                            st.session_state.ftp_edit_mode = False
                            st.session_state.clear_form = True  # Flag to indicate form should be cleared
                            st.rerun()
                        else:
                            st.error(f"Failed to update FTP server {host}")
                    else:
                        # Add new FTP setting
                        new_id = db.add_ftp_setting(ftp_data)
                        if new_id:
                            st.success(f"FTP server {host} added successfully")
                            # Reset the form by clearing temp variables
                            st.session_state.temp_host = ""
                            st.session_state.temp_port = 21
                            st.session_state.temp_username = ""
                            st.session_state.temp_password = ""
                            st.session_state.temp_is_default = False
                            st.session_state.clear_form = True  # Flag to indicate form should be cleared
                            st.rerun()
                        else:
                            st.error(f"Failed to add FTP server {host}")
            
            if test_button:
                if not host:
                    st.error("FTP Host is required")
                elif not username:
                    st.error("Username is required")
                elif not password:
                    st.error("Password is required")
                else:
                    ftp_data = {
                        'host': host,
                        'port': port,
                        'username': username,
                        'password': password
                    }
                    
                    with st.spinner("Testing FTP connection..."):
                        success, message = test_ftp_connection(ftp_data)
                        if success:
                            st.success(message)
                            # Store the test values in temp variables for potential saving
                            st.session_state.temp_host = host
                            st.session_state.temp_port = port
                            st.session_state.temp_username = username
                            st.session_state.temp_password = password
                        else:
                            st.error(message)
        
        # Cancel button outside the form
        if st.button("Cancel", key="cancel_button"):
            # Reset the form by clearing temp variables
            st.session_state.temp_host = ""
            st.session_state.temp_port = 21
            st.session_state.temp_username = ""
            st.session_state.temp_password = ""
            st.session_state.temp_is_default = False
            st.session_state.ftp_edit_id = None
            st.session_state.ftp_edit_mode = False
            st.rerun()

        # Show a note about FTP security
        st.markdown("""
        > **Note:** FTP credentials are stored in the database. While passwords are stored securely, 
        FTP itself is not encrypted. For sensitive transfers, consider using SFTP or FTPS instead.
        """)

    with tab2:
        st.header("General Settings")
        st.info("General application settings will be available here in future updates.")

    # Bottom actions section
    st.markdown("---")
    st.caption("© 2023 Product Generator. All rights reserved.")

import os
import ftplib
import io
import streamlit as st
from datetime import datetime
import tempfile

def upload_to_ftp(data, filename, ftp_settings):
    """
    Upload data to an FTP server
    
    Args:
        data (str or bytes): CSV data or other content to upload
        filename (str): Name of the file to create on the FTP server
        ftp_settings (dict): Dictionary containing FTP credentials
            - host: FTP server hostname
            - port: FTP server port
            - username: FTP username
            - password: FTP password
            
    Returns:
        tuple: (success, message) where success is a boolean and message is a string
    """
    if not ftp_settings:
        return False, "No FTP settings provided"
    
    try:
        # Connect to the FTP server
        with ftplib.FTP() as ftp:
            # Connect with timeout
            ftp.connect(
                host=ftp_settings['host'],
                port=int(ftp_settings['port']),
                timeout=30
            )
            
            # Login
            ftp.login(
                user=ftp_settings['username'],
                passwd=ftp_settings['password']
            )
            
            # Log welcome message
            welcome_msg = ftp.getwelcome()
            st.info(f"Connected to FTP server: {welcome_msg}")
            
            # Check if data is string or bytes and handle accordingly
            if isinstance(data, str):
                # Create a temporary file in text mode for string data
                with tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8', delete=False) as temp_file:
                    temp_file.write(data)
                    temp_file.flush()
                    temp_file_path = temp_file.name
            else:
                # Create a temporary file in binary mode for bytes data
                with tempfile.NamedTemporaryFile(mode='wb+', delete=False) as temp_file:
                    temp_file.write(data)
                    temp_file.flush()
                    temp_file_path = temp_file.name
            
            # Upload the file
            with open(temp_file_path, 'rb') as file:
                ftp.storbinary(f'STOR {filename}', file)
            
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass
                
            return True, f"File '{filename}' uploaded successfully to {ftp_settings['host']}"
    except ftplib.all_errors as e:
        error_message = str(e)
        
        # Provide more user-friendly error messages for common issues
        if "connection" in error_message.lower():
            return False, f"Failed to connect to FTP server: {error_message}"
        elif "login" in error_message.lower() or "authentication" in error_message.lower():
            return False, f"FTP authentication failed: {error_message}"
        elif "permission" in error_message.lower():
            return False, f"FTP permission denied: {error_message}"
        else:
            return False, f"FTP error: {error_message}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def test_ftp_connection(ftp_settings):
    """
    Test connection to FTP server
    
    Args:
        ftp_settings (dict): Dictionary containing FTP credentials
            
    Returns:
        tuple: (success, message) where success is a boolean and message is a string
    """
    if not ftp_settings:
        return False, "No FTP settings provided"
    
    try:
        # Connect to the FTP server
        with ftplib.FTP() as ftp:
            # Connect with timeout
            ftp.connect(
                host=ftp_settings['host'],
                port=int(ftp_settings['port']),
                timeout=10
            )
            
            # Login
            ftp.login(
                user=ftp_settings['username'],
                passwd=ftp_settings['password']
            )
            
            # Log welcome message
            welcome_msg = ftp.getwelcome()
            
            # Try to list directory to ensure we have proper permissions
            dir_list = ftp.nlst()
            
            return True, f"Connected successfully to {ftp_settings['host']}. Server message: {welcome_msg}"
    except ftplib.all_errors as e:
        error_message = str(e)
        
        # Provide more user-friendly error messages for common issues
        if "connection" in error_message.lower():
            return False, f"Failed to connect to FTP server: {error_message}"
        elif "login" in error_message.lower() or "authentication" in error_message.lower():
            return False, f"FTP authentication failed: {error_message}"
        elif "permission" in error_message.lower():
            return False, f"FTP permission denied: {error_message}"
        else:
            return False, f"FTP error: {error_message}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

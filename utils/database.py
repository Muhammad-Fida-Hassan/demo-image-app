import mysql.connector
from mysql.connector import Error
from mysql.connector import pooling
import streamlit as st
import pandas as pd
from config import DB_CONFIG
import os
import sys
import time

# Global connection pool - will be initialized once and reused
connection_pool = None

def init_connection_pool():
    """Initialize a connection pool that can be shared across sessions"""
    global connection_pool
    if connection_pool is not None:
        return connection_pool
         
    try:
        # Configure pool with connection parameters
        pool_config = {
            'pool_name': 'demo_image_app_pool',
            'pool_size': 5,  # Adjust based on your needs and server limits
            'pool_reset_session': True,
            'host': DB_CONFIG['host'],
            'port': DB_CONFIG.get('port', 3306),
            'database': DB_CONFIG['database'],
            'user': DB_CONFIG['user'],
            'password': DB_CONFIG['password'],
            'use_pure': True,
        } 
        
        # Add SSL configuration if needed
        if DB_CONFIG.get('ssl_mode') == 'REQUIRED' and os.path.exists(DB_CONFIG.get('ssl_ca', '')):
            pool_config.update({
                'ssl_ca': DB_CONFIG['ssl_ca'],
                'ssl_verify_cert': DB_CONFIG.get('ssl_verify', True),
            })
            
        # Create the pool
        connection_pool = mysql.connector.pooling.MySQLConnectionPool(**pool_config)
        st.success(f"Connection pool initialized with size: {pool_config['pool_size']}")
        return connection_pool
    except Error as e:
        st.error(f"Error creating connection pool: {e}")
        return None

class Database:
    def __init__(self):
        """Initialize database connection"""
        self.connection = None
        self.cursor = None
        self.max_reconnect_attempts = 3
        self.reconnect_delay = 2  # seconds
        
        # Get a connection from the pool instead of creating a new one
        self._get_connection_from_pool()
        
    def _get_connection_from_pool(self):
        """Get a connection from the connection pool"""
        global connection_pool
        
        try:
            # Initialize the pool if it doesn't exist
            if connection_pool is None:
                connection_pool = init_connection_pool()
            
            if connection_pool is None:
                # If pool initialization failed, fall back to direct connection methods
                if not self._connect_with_ssl():
                    if not self._connect_without_ssl_verify():
                        self._connect_without_ssl()
                return
                
            # Get a connection from the pool
            self.connection = connection_pool.get_connection()
            if self.connection.is_connected():
                self.cursor = self.connection.cursor(dictionary=True)
                server_info = self.connection.get_server_info()
                st.success(f"Connected to MySQL server version {server_info} (pooled connection)")
                
                # Create tables if they don't exist
                self._create_tables()
        except Error as e:
            st.warning(f"Pool connection failed: {e}. Trying direct connection methods...")
            # Fall back to direct connection methods
            if not self._connect_with_ssl():
                if not self._connect_without_ssl_verify():
                    self._connect_without_ssl()

    def _connect_with_ssl(self):
        """Try to connect with SSL"""
        try:
            # SSL configuration with verification
            ssl_config = {}
            if DB_CONFIG.get('ssl_mode') == 'REQUIRED' and os.path.exists(DB_CONFIG.get('ssl_ca', '')):
                ssl_config = {
                    'ssl_ca': DB_CONFIG['ssl_ca'],
                    'ssl_verify_cert': DB_CONFIG.get('ssl_verify', True),
                }
                st.info(f"Attempting connection with SSL certificate: {DB_CONFIG['ssl_ca']}")
            
            # Connect to database with SSL
            self.connection = mysql.connector.connect(
                host=DB_CONFIG['host'],
                port=DB_CONFIG.get('port', 3306),
                database=DB_CONFIG['database'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                **ssl_config
            )
            
            if self.connection.is_connected():
                self.cursor = self.connection.cursor(dictionary=True)
                server_info = self.connection.get_server_info()
                st.success(f"Connected to MySQL server version {server_info} with SSL")
                
                # Create tables if they don't exist
                self._create_tables()
                return True
            return False
        except Error as e:
            st.warning(f"SSL connection attempt failed: {e}")
            return False
    
    def _connect_without_ssl_verify(self):
        """Try to connect with SSL but without verification"""
        try:
            # SSL configuration without verification
            ssl_config = {
                'ssl_ca': DB_CONFIG.get('ssl_ca', ''),
                'ssl_verify_cert': False,
            }
            st.info("Attempting connection with SSL but without certificate verification")
            
            # Connect to database with SSL but without verification
            self.connection = mysql.connector.connect(
                host=DB_CONFIG['host'],
                port=DB_CONFIG.get('port', 3306),
                database=DB_CONFIG['database'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                **ssl_config
            )
            
            if self.connection.is_connected():
                self.cursor = self.connection.cursor(dictionary=True)
                server_info = self.connection.get_server_info()
                st.success(f"Connected to MySQL server version {server_info} with SSL (no verification)")
                
                # Create tables if they don't exist
                self._create_tables()
                return True
            return False
        except Error as e:
            st.warning(f"SSL without verification connection attempt failed: {e}")
            return False
    
    def _connect_without_ssl(self):
        """Try to connect without SSL as last resort"""
        try:
            st.info("Attempting connection without SSL as last resort")
            
            # Connect to database without SSL
            self.connection = mysql.connector.connect(
                host=DB_CONFIG['host'],
                port=DB_CONFIG.get('port', 3306),
                database=DB_CONFIG['database'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                use_pure=True  # Use pure Python implementation
            )
            
            if self.connection.is_connected():
                self.cursor = self.connection.cursor(dictionary=True)
                server_info = self.connection.get_server_info()
                st.success(f"Connected to MySQL server version {server_info} without SSL")
                
                # Create tables if they don't exist
                self._create_tables()
                return True
            
            st.error("All connection attempts failed. Please check your database configuration.")
            return False
        except Error as e:
            st.error(f"Connection without SSL failed: {e}")
            return False

    def _check_connection(self):
        """Check if connection is alive and reconnect if necessary"""
        try:
            if self.connection is None or not self.connection.is_connected():
                st.warning("Database connection lost. Attempting to reconnect...")
                return self.reconnect()
            return True
        except Error as e:
            st.warning(f"Connection check failed: {e}")
            return self.reconnect()
    
    def reconnect(self):
        """Attempt to reconnect to the database"""
        attempts = 0
        
        while attempts < self.max_reconnect_attempts:
            try:
                attempts += 1
                st.info(f"Reconnection attempt {attempts}/{self.max_reconnect_attempts}...")
                
                # Close existing connections if they exist
                if hasattr(self, 'cursor') and self.cursor is not None:
                    try:
                        self.cursor.close()
                    except:
                        pass
                    
                if hasattr(self, 'connection') and self.connection is not None:
                    try:
                        self.connection.close()
                    except:
                        pass
                
                # Reset connection attributes
                self.connection = None
                self.cursor = None
                
                # Try reconnecting with the same strategy as in __init__
                if self._connect_with_ssl():
                    return True
                if self._connect_without_ssl_verify():
                    return True
                if self._connect_without_ssl():
                    return True
                
                # If we reach here, reconnection failed
                st.warning(f"Reconnection attempt {attempts} failed. Retrying in {self.reconnect_delay} seconds...")
                time.sleep(self.reconnect_delay)
                
            except Exception as e:
                st.warning(f"Reconnection error: {e}. Retrying in {self.reconnect_delay} seconds...")
                time.sleep(self.reconnect_delay)
                
        st.error("Failed to reconnect to database after multiple attempts.")
        return False

    def _create_tables(self):
        """Create necessary tables if they don't exist"""
        if not self.cursor:
            st.error("No database cursor available. Tables not created.")
            return
            
        create_products_table = """
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_name VARCHAR(255) NOT NULL,
            item_sku VARCHAR(100) NOT NULL,
            parent_child ENUM('Parent', 'Child') NOT NULL,
            parent_sku VARCHAR(100) NULL,
            size TEXT NULL,
            color TEXT NULL,
            image_url TEXT NULL,
            marketplace_title TEXT NULL,
            category VARCHAR(1000) NULL,
            tax_class VARCHAR(50) NULL,
            quantity INT NOT NULL DEFAULT 0,
            price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            mockup_id VARCHAR(100) NULL,
            smart_object_uuid VARCHAR(100) NULL,
            mockup_ids TEXT NULL,
            smart_object_uuids TEXT NULL
        )
        """
        self.cursor.execute(create_products_table)
        
        # Create generated_products table if it doesn't exist
        create_generated_products_table = """
        CREATE TABLE IF NOT EXISTS generated_products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_name VARCHAR(255) NOT NULL,
            item_sku VARCHAR(100) NULL,
            marketplace_title TEXT NULL,
            size TEXT NULL,
            color TEXT NULL,
            original_design_url TEXT NULL,
            mockup_urls TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_published BOOLEAN DEFAULT FALSE,
            parent_product_id INT NULL,
            parent_sku VARCHAR(100) NULL,
            parent_child VARCHAR(10) DEFAULT 'Child',

            INDEX idx_item_sku (item_sku),
            INDEX idx_parent_sku (parent_sku),
            INDEX idx_created_at (created_at),
            INDEX idx_is_published (is_published),
            INDEX idx_parent_product_id (parent_product_id)
        )
        """
        self.cursor.execute(create_generated_products_table)
        
        # Create ftp_settings table if it doesn't exist
        create_ftp_settings_table = """
        CREATE TABLE IF NOT EXISTS ftp_settings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            host VARCHAR(255) NOT NULL,
            port INT NOT NULL DEFAULT 21,
            username VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        self.cursor.execute(create_ftp_settings_table)
        self.connection.commit()
        
        # Check if columns exist and add them if they don't
        try:
            # Check if mockup_id column exists
            self.cursor.execute("SHOW COLUMNS FROM products LIKE 'mockup_id'")
            if not self.cursor.fetchone():
                self.cursor.execute("ALTER TABLE products ADD COLUMN mockup_id VARCHAR(255) NULL")
            
            # Check if smart_object_uuid column exists
            self.cursor.execute("SHOW COLUMNS FROM products LIKE 'smart_object_uuid'")
            if not self.cursor.fetchone():
                self.cursor.execute("ALTER TABLE products ADD COLUMN smart_object_uuid VARCHAR(255) NULL")
            
            # Check if item_sku column exists in generated_products
            self.cursor.execute("SHOW COLUMNS FROM generated_products LIKE 'item_sku'")
            if not self.cursor.fetchone():
                self.cursor.execute("ALTER TABLE generated_products ADD COLUMN item_sku VARCHAR(100) NULL")
                self.cursor.execute("ALTER TABLE generated_products ADD INDEX idx_item_sku (item_sku)")
            
            # Check if parent_sku column exists in generated_products
            self.cursor.execute("SHOW COLUMNS FROM generated_products LIKE 'parent_sku'")
            if not self.cursor.fetchone():
                self.cursor.execute("ALTER TABLE generated_products ADD COLUMN parent_sku VARCHAR(100) NULL")
                
            # Check if mockup_ids column exists
            self.cursor.execute("SHOW COLUMNS FROM products LIKE 'mockup_ids'")
            if not self.cursor.fetchone():
                self.cursor.execute("ALTER TABLE products ADD COLUMN mockup_ids TEXT NULL")
            
            # Check if smart_object_uuids column exists
            self.cursor.execute("SHOW COLUMNS FROM products LIKE 'smart_object_uuids'")
            if not self.cursor.fetchone():
                self.cursor.execute("ALTER TABLE products ADD COLUMN smart_object_uuids TEXT NULL")
            
            self.connection.commit()
        except Error as e:
            st.error(f"Error modifying tables: {e}")
        
        self.connection.commit()
        
        # Alter table to modify columns if they already exist with smaller size
        try:
            alter_size_query = "ALTER TABLE products MODIFY COLUMN size TEXT"
            self.cursor.execute(alter_size_query)
            
            alter_color_query = "ALTER TABLE products MODIFY COLUMN color TEXT"
            self.cursor.execute(alter_color_query)
            
            # Add mockup_id and smart_object_uuid columns if they don't exist
            check_column_query = """
            SELECT COUNT(*) as column_exists FROM information_schema.columns 
            WHERE table_schema = DATABASE() AND table_name = 'products' AND column_name = 'mockup_id'
            """
            self.cursor.execute(check_column_query)
            result = self.cursor.fetchone()
            
            if result and result['column_exists'] == 0:
                add_column_query = """
                ALTER TABLE products 
                ADD COLUMN mockup_id VARCHAR(100) NULL,
                ADD COLUMN smart_object_uuid VARCHAR(100) NULL
                """
                self.cursor.execute(add_column_query)
                
            self.connection.commit()
        except Error as e:
            st.warning(f"Table alteration notice: {e}")
    
    def add_product(self, product_data):
        """
        Add a new product to the database
        
        Args:
            product_data (dict): Product data dictionary
            
        Returns:
            int: Product ID if inserted successfully, None otherwise
        """
        if not self._check_connection():
            st.error("Cannot add product: database connection failed")
            return None
            
        try:
            query = """
            INSERT INTO products (
                product_name, item_sku, parent_child, parent_sku, size, color, 
                image_url, marketplace_title, category, tax_class, quantity, price,
                mockup_id, smart_object_uuid, mockup_ids, smart_object_uuids
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                product_data['product_name'],
                product_data['item_sku'],
                product_data['parent_child'],
                product_data['parent_sku'],
                product_data['size'],
                product_data['color'],
                product_data['image_url'],
                product_data['marketplace_title'],
                product_data['category'],
                product_data['tax_class'],
                product_data['quantity'],
                product_data['price'],
                product_data['mockup_id'],
                product_data['smart_object_uuid'],
                product_data.get('mockup_ids', None),
                product_data.get('smart_object_uuids', None),
            )
            
            self.cursor.execute(query, values)
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            st.error(f"Error adding product: {e}")
            return None
    
    def get_all_products(self):
        """
        Get all products from database
        
        Returns:
            DataFrame: Products as pandas DataFrame or None if error
        """
        if not self._check_connection():
            st.error("Cannot get products: database connection failed")
            return pd.DataFrame()
            
        try:
            if not self.cursor:
                st.error("No database cursor available. Cannot get products.")
                return pd.DataFrame()
                
            query = "SELECT * FROM products ORDER BY created_at DESC"
            self.cursor.execute(query)
            result = self.cursor.fetchall()
            df = pd.DataFrame(result) if result else pd.DataFrame()
            
            # Ensure image_url is properly formatted if using S3
            # This ensures any relative paths are converted to absolute when needed
            # but preserves S3 URLs as they are
            if not df.empty and 'image_url' in df.columns:
                from utils.api import is_s3_url
                import os
                
                def format_image_url(url):
                    if not url:
                        return url
                    if is_s3_url(url):
                        return url  # S3 URLs are already complete
                    # Convert relative paths to absolute if needed
                    elif os.path.exists(url):
                        return os.path.abspath(url)
                    return url
                
                df['image_url'] = df['image_url'].apply(format_image_url)
            
            return df
        except Error as e:
            st.error(f"Error retrieving products: {e}")
            return pd.DataFrame()
    
    def get_product(self, product_id):
        """
        Get a specific product by ID
        
        Args:
            product_id (int): Product ID
            
        Returns:
            dict: Product data or None if not found
        """
        if not self._check_connection():
            st.error(f"Cannot get product {product_id}: database connection failed")
            return None
            
        try:
            query = "SELECT * FROM products WHERE id = %s"
            self.cursor.execute(query, (product_id,))
            return self.cursor.fetchone()
        except Error as e:
            st.error(f"Error retrieving product {product_id}: {e}")
            return None
    
    def update_product(self, product_id, product_data):
        """
        Update a product
        
        Args:
            product_id (int): Product ID to update
            product_data (dict): Updated product data
            
        Returns:
            bool: True if update successful, False otherwise
        """
        if not self._check_connection():
            st.error(f"Cannot update product {product_id}: database connection failed")
            return False
            
        try:
            query = """
            UPDATE products SET
                product_name = %s,
                item_sku = %s,
                parent_child = %s,
                parent_sku = %s,
                size = %s,
                color = %s,
                image_url = %s,
                marketplace_title = %s,
                category = %s,
                tax_class = %s,
                quantity = %s,
                price = %s,
                mockup_id = %s,
                smart_object_uuid = %s,
                mockup_ids = %s,
                smart_object_uuids = %s
            WHERE id = %s
            """
            values = (
                product_data['product_name'],
                product_data['item_sku'],
                product_data['parent_child'],
                product_data['parent_sku'],
                product_data['size'],
                product_data['color'],
                product_data['image_url'],
                product_data['marketplace_title'],
                product_data['category'],
                product_data['tax_class'],
                product_data['quantity'],
                product_data['price'],
                product_data['mockup_id'],
                product_data['smart_object_uuid'],
                product_data.get('mockup_ids', None),
                product_data.get('smart_object_uuids', None),
                product_id
            )
            
            self.cursor.execute(query, values)
            self.connection.commit()
            return True
        except Error as e:
            st.error(f"Error updating product {product_id}: {e}")
            return False
            
    def create_generated_product(self, product_data):
        """
        Add a new generated product to the database
        
        Args:
            product_data (dict): Generated product data containing:
                - product_name: Name of the product
                - item_sku: Unique SKU for the design (was design_sku)
                - marketplace_title: Title for marketplace listings
                - size: JSON string of available sizes
                - color: JSON string of available colors (hex values)
                - original_design_url: URL to the original design in S3
                - mockup_urls: JSON string mapping color hex codes to S3 mockup URLs
                - parent_product_id: Optional reference to a parent product
            
        Returns:
            int: Product ID if inserted successfully, None otherwise
        """
        if not self._check_connection():
            st.error("Cannot add generated product: database connection failed")
            return None
            
        try:
            # Check if the table exists, create it if not
            self._ensure_generated_products_table()
            
            # Validate required fields
            if 'product_name' not in product_data:
                st.error("Missing required field: product_name")
                return None
                
            # Handle case where design_sku is provided instead of item_sku
            if 'item_sku' not in product_data and 'design_sku' in product_data:
                product_data['item_sku'] = product_data['design_sku']
                st.info(f"Using design_sku as item_sku: {product_data['item_sku']}")
            
            if 'item_sku' not in product_data:
                st.error("Missing required field: item_sku")
                return None
            
            # Check if SKU already exists to avoid duplicates
            query = "SELECT COUNT(*) as count FROM generated_products WHERE item_sku = %s"
            self.cursor.execute(query, (product_data['item_sku'],))
            result = self.cursor.fetchone()
            if result and result['count'] > 0:
                st.warning(f"SKU {product_data['item_sku']} already exists in database. Using it anyway.")
            
            # Set parent_sku based on parent_product_id if available
            parent_sku = product_data.get('parent_sku', '')
            if not parent_sku and 'parent_product_id' in product_data and product_data['parent_product_id']:
                # Fetch parent product's SKU
                parent_query = "SELECT item_sku FROM products WHERE id = %s"
                self.cursor.execute(parent_query, (product_data['parent_product_id'],))
                parent_result = self.cursor.fetchone()
                if parent_result:
                    parent_sku = parent_result['item_sku']
                
            query = """
            INSERT INTO generated_products (
                product_name, parent_sku, marketplace_title, size, color,
                original_design_url, mockup_urls, is_published, parent_product_id, item_sku
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # Default to not published
            is_published = product_data.get('is_published', False)
            
            values = (
                product_data['product_name'],
                parent_sku,  # Use the determined parent_sku
                product_data.get('marketplace_title', ''),
                product_data.get('size', '[]'),
                product_data.get('color', '[]'),
                product_data.get('original_design_url', ''),
                product_data.get('mockup_urls', '{}'),
                is_published,
                product_data.get('parent_product_id', None),
                product_data['item_sku']  # Make sure item_sku is included
            )
            
            self.cursor.execute(query, values)
            self.connection.commit()
            new_id = self.cursor.lastrowid
            st.success(f"Generated product '{product_data['product_name']}' added with ID: {new_id}")
            return new_id
        except KeyError as e:
            st.error(f"Error adding generated product - missing required field: {e}")
            return None
        except Error as e:
            st.error(f"Error adding generated product: {e}")
            return None
    
    def update_generated_product(self, product_id, product_data):
        """
        Update a generated product
        
        Args:
            product_id (int): Generated Product ID to update
            product_data (dict): Updated product data
            
        Returns:
            bool: True if update successful, False otherwise
        """
        if not self._check_connection():
            st.error(f"Cannot update generated product {product_id}: database connection failed")
            return False
            
        try:
            query = """
            UPDATE generated_products SET
                product_name = %s,
                item_sku = %s,
                parent_sku = %s,
                marketplace_title = %s,
                size = %s,
                color = %s,
                original_design_url = %s,
                mockup_urls = %s,
                is_published = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            
            # Default to current published state if not specified
            is_published = product_data.get('is_published', False)
            
            values = (
                product_data['product_name'],
                product_data.get('item_sku', ''),
                product_data.get('parent_sku', ''),
                product_data.get('marketplace_title', ''),
                product_data.get('size', '[]'),
                product_data.get('color', '[]'),
                product_data.get('original_design_url', ''),
                product_data.get('mockup_urls', '{}'),
                is_published,
                product_id
            )
            
            self.cursor.execute(query, values)
            self.connection.commit()
            return True
        except Error as e:
            st.error(f"Error updating generated product {product_id}: {e}")
            return False
    
    def get_all_generated_products(self):
        """
        Get all generated products from database
        
        Returns:
            DataFrame: Generated products as pandas DataFrame or None if error
        """
        if not self._check_connection():
            st.error("Cannot get generated products: database connection failed")
            return pd.DataFrame()
            
        try:
            # Ensure the table exists
            self._ensure_generated_products_table()
            
            query = "SELECT * FROM generated_products ORDER BY created_at DESC"
            self.cursor.execute(query)
            result = self.cursor.fetchall()
            return pd.DataFrame(result) if result else pd.DataFrame()
        except Error as e:
            st.error(f"Error retrieving generated products: {e}")
            return pd.DataFrame()
    
    def get_generated_product(self, product_id):
        """
        Get a specific generated product by ID
        
        Args:
            product_id (int): Generated Product ID
            
        Returns:
            dict: Product data or None if not found
        """
        if not self._check_connection():
            st.error(f"Cannot get generated product {product_id}: database connection failed")
            return None
            
        try:
            query = "SELECT * FROM generated_products WHERE id = %s"
            self.cursor.execute(query, (product_id,))
            return self.cursor.fetchone()
        except Error as e:
            st.error(f"Error retrieving generated product {product_id}: {e}")
            return None
            
    def _ensure_generated_products_table(self):
        """Create the generated_products table if it doesn't exist"""
        try:
            # This is now handled in _create_tables() during initialization
            # Keep this method for backward compatibility with existing code
            pass
        except Error as e:
            st.warning(f"Table creation notice: {e}")

    def delete_product(self, product_id):
        """
        Delete a product
        
        Args:
            product_id (int): Product ID to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        if not self._check_connection():
            st.error(f"Cannot delete product {product_id}: database connection failed")
            return False
            
        try:
            query = "DELETE FROM products WHERE id = %s"
            self.cursor.execute(query, (product_id,))
            self.connection.commit()
            return True
        except Error as e:
            st.error(f"Error deleting product {product_id}: {e}")
            return False

    def delete_generated_product(self, product_id):
        """
        Delete a generated product
        
        Args:
            product_id (int): Generated Product ID to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        if not self._check_connection():
            st.error(f"Cannot delete generated product {product_id}: database connection failed")
            return False
            
        try:
            query = "DELETE FROM generated_products WHERE id = %s"
            self.cursor.execute(query, (product_id,))
            self.connection.commit()
            return True
        except Error as e:
            st.error(f"Error deleting generated product {product_id}: {e}")
            return False
    
    def get_stats(self):
        """
        Get basic statistics for dashboard
        
        Returns:
            dict: Dictionary containing stats
        """
        if not self._check_connection():
            st.error("Cannot get stats: database connection failed")
            return {
                'total_products': 0,
                'parent_count': 0,
                'image_count': 0
            }
            
        try:
            # Total products
            self.cursor.execute("SELECT COUNT(*) as total FROM products")
            total_products = self.cursor.fetchone()['total']
            
            # Total parent products
            self.cursor.execute("SELECT COUNT(*) as parent_count FROM products WHERE parent_child = 'Parent'")
            parent_count = self.cursor.fetchone()['parent_count']
            
            # Total images stored
            self.cursor.execute("SELECT COUNT(*) as image_count FROM products WHERE image_url IS NOT NULL")
            image_count = self.cursor.fetchone()['image_count']
            
            return {
                'total_products': total_products,
                'parent_count': parent_count,
                'image_count': image_count
            }
        except Error as e:
            st.error(f"Error getting stats: {e}")
            return {
                'total_products': 0,
                'parent_count': 0,
                'image_count': 0
            }
    
    def check_if_sku_exists(self, sku):
        """
        Check if a SKU already exists in the database
        
        Args:
            sku (str): The SKU to check
            
        Returns:
            bool: True if the SKU exists, False otherwise
        """
        if not self._check_connection():
            st.error(f"Cannot check SKU {sku}: database connection failed")
            return False
            
        try:
            # Use the existing cursor
            cursor = self.cursor if hasattr(self, 'cursor') else self.connection.cursor()
            
            # Execute query to check if SKU exists in generated_products table
            cursor.execute(
                "SELECT COUNT(*) as count FROM generated_products WHERE item_sku = %s OR parent_sku = %s", 
                (sku, sku)
            )
            
            # Get the result
            result = cursor.fetchone()
            count = result['count'] if isinstance(result, dict) else result[0]
            
            return count > 0
        except Exception as e:
            st.error(f"Error checking if SKU exists: {e}")
            return False

    def get_related_products_by_design(self, design_url, exclude_id=None):
        """Get all generated products that use the same original design"""
        try:
            query = """
                SELECT * FROM generated_products 
                WHERE original_design_url = %s
            """
            params = [design_url]
            
            # Exclude the current product if specified
            if exclude_id is not None:
                query += " AND id != %s"
                params.append(exclude_id)
                
            # Order by id to get a consistent order
            query += " ORDER BY id"
            
            self.cursor.execute(query, params)
            columns = [col[0] for col in self.cursor.description]
            result = [dict(zip(columns, row)) for row in self.cursor.fetchall()]
            return pd.DataFrame(result)
        except Exception as e:
            print(f"Error getting related products: {e}")
            return pd.DataFrame()
    
    def get_product_count(self):
        """
        Get the total number of products in the database
        
        Returns:
            int: Total number of products
        """
        if not self._check_connection():
            st.error("Cannot get product count: database connection failed")
            return 0
            
        try:
            query = "SELECT COUNT(*) as count FROM products"
            self.cursor.execute(query)
            result = self.cursor.fetchone()
            return result['count'] if result else 0
        except Error as e:
            st.error(f"Error getting product count: {e}")
            return 0
    
    def __del__(self):
        """Close database connection when object is destroyed"""
        if hasattr(self, 'connection') and self.connection is not None:
            try:
                if hasattr(self, 'cursor') and self.cursor is not None:
                    self.cursor.close()
                if self.connection.is_connected():
                    self.connection.close()
            except:
                pass

    # FTP Settings methods
    def get_ftp_settings(self):
        """
        Get all FTP settings from database
        
        Returns:
            DataFrame: FTP settings as pandas DataFrame or empty DataFrame if none exist
        """
        if not self._check_connection():
            st.error("Cannot get FTP settings: database connection failed")
            return pd.DataFrame()
            
        try:
            query = "SELECT * FROM ftp_settings ORDER BY is_default DESC, created_at DESC"
            self.cursor.execute(query)
            result = self.cursor.fetchall()
            return pd.DataFrame(result) if result else pd.DataFrame()
        except Error as e:
            st.error(f"Error retrieving FTP settings: {e}")
            return pd.DataFrame()
    
    def get_default_ftp_settings(self):
        """
        Get default FTP settings
        
        Returns:
            dict: Default FTP settings or None if not found
        """
        if not self._check_connection():
            st.error("Cannot get default FTP settings: database connection failed")
            return None
            
        try:
            query = "SELECT * FROM ftp_settings WHERE is_default = TRUE LIMIT 1"
            self.cursor.execute(query)
            result = self.cursor.fetchone()
            
            if not result:
                # If no default, get the most recent
                query = "SELECT * FROM ftp_settings ORDER BY created_at DESC LIMIT 1"
                self.cursor.execute(query)
                result = self.cursor.fetchone()
                
            return result
        except Error as e:
            st.error(f"Error retrieving default FTP settings: {e}")
            return None
    
    def get_ftp_setting(self, setting_id):
        """
        Get specific FTP setting by ID
        
        Args:
            setting_id (int): FTP setting ID
            
        Returns:
            dict: FTP setting or None if not found
        """
        if not self._check_connection():
            st.error(f"Cannot get FTP setting {setting_id}: database connection failed")
            return None
            
        try:
            query = "SELECT * FROM ftp_settings WHERE id = %s"
            self.cursor.execute(query, (setting_id,))
            return self.cursor.fetchone()
        except Error as e:
            st.error(f"Error retrieving FTP setting {setting_id}: {e}")
            return None
    
    def add_ftp_setting(self, ftp_data):
        """
        Add a new FTP setting to the database
        
        Args:
            ftp_data (dict): FTP setting data including host, port, username, password
            
        Returns:
            int: FTP setting ID if inserted successfully, None otherwise
        """
        if not self._check_connection():
            st.error("Cannot add FTP setting: database connection failed")
            return None
            
        try:
            # If this is set as default, clear any existing defaults
            if ftp_data.get('is_default', False):
                self.cursor.execute("UPDATE ftp_settings SET is_default = FALSE")
            
            query = """
            INSERT INTO ftp_settings (
                host, port, username, password, is_default
            ) VALUES (%s, %s, %s, %s, %s)
            """
            values = (
                ftp_data['host'],
                ftp_data['port'],
                ftp_data['username'],
                ftp_data['password'],
                ftp_data.get('is_default', False)
            )
            
            self.cursor.execute(query, values)
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            st.error(f"Error adding FTP setting: {e}")
            return None
    
    def update_ftp_setting(self, setting_id, ftp_data):
        """
        Update an FTP setting
        
        Args:
            setting_id (int): FTP setting ID to update
            ftp_data (dict): Updated FTP data
            
        Returns:
            bool: True if update successful, False otherwise
        """
        if not self._check_connection():
            st.error(f"Cannot update FTP setting {setting_id}: database connection failed")
            return False
            
        try:
            # If this is set as default, clear any existing defaults
            if ftp_data.get('is_default', False):
                self.cursor.execute("UPDATE ftp_settings SET is_default = FALSE")
            
            query = """
            UPDATE ftp_settings SET
                host = %s,
                port = %s,
                username = %s,
                password = %s,
                is_default = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            
            values = (
                ftp_data['host'],
                ftp_data['port'],
                ftp_data['username'],
                ftp_data['password'],
                ftp_data.get('is_default', False),
                setting_id
            )
            
            self.cursor.execute(query, values)
            self.connection.commit()
            return True
        except Error as e:
            st.error(f"Error updating FTP setting {setting_id}: {e}")
            return False
    
    def delete_ftp_setting(self, setting_id):
        """
        Delete an FTP setting
        
        Args:
            setting_id (int): FTP setting ID to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        if not self._check_connection():
            st.error(f"Cannot delete FTP setting {setting_id}: database connection failed")
            return False
            
        try:
            query = "DELETE FROM ftp_settings WHERE id = %s"
            self.cursor.execute(query, (setting_id,))
            self.connection.commit()
            return True
        except Error as e:
            st.error(f"Error deleting FTP setting {setting_id}: {e}")
            return False
            
    def set_ftp_setting_as_default(self, setting_id):
        """
        Set an FTP setting as the default
        
        Args:
            setting_id (int): FTP setting ID to set as default
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._check_connection():
            st.error(f"Cannot set FTP setting {setting_id} as default: database connection failed")
            return False
            
        try:
            # Clear any existing defaults
            self.cursor.execute("UPDATE ftp_settings SET is_default = FALSE")
            
            # Set this one as default
            query = "UPDATE ftp_settings SET is_default = TRUE WHERE id = %s"
            self.cursor.execute(query, (setting_id,))
            self.connection.commit()
            return True
        except Error as e:
            st.error(f"Error setting FTP setting {setting_id} as default: {e}")
            return False

# Create connection pool
@st.cache_resource
def get_database_connection():
    """
    Get a cached database connection
    
    Returns:
        Database: Database connection instance
    """
    # Initialize the connection pool first if it doesn't exist
    if connection_pool is None:
        init_connection_pool()
        
    return Database()

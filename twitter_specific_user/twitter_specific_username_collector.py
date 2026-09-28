import logging
import os
import requests
import pandas as pd
import random
import time
import pymssql
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ----------------------------------- #
# Load environment variables
# ----------------------------------- #
load_dotenv()

# ----------------------------------- #
# Constants and configurations
# ----------------------------------- #
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")

DOMAIN = os.getenv("DOMAIN")
#DOMAIN = "https://x.com/"

MAX_PAGES = 50  
MAX_TOTAL_FAILURES = 10  
LOG_DIR = "logs"

# ----------------------------------- #
# Connect to SQL Server Database
# ----------------------------------- #
def connect_master():
    try:
        conn = pymssql.connect(server=DB_HOST, database="master")
        print("\u2705 Connected to SQL Server (master).")
        return conn
    except Exception as e:
        print(f"\u274C Error connecting to SQL Server master: {e}")
        exit()

def connect_to_database():
    try:
        connection = pymssql.connect(
            server = DB_HOST,
            database = DB_NAME,
            autocommit= True
        )
        print("\u2705 Connected to SQL Server database successfully!")
        return connection
    except Exception as e:
        print(f"\u274C Error connecting to SQL Server database: {e}")
        exit()

# ----------------------------------- #
# Configure logging
# ----------------------------------- #
def configure_logging():
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
    except Exception as e:
        print(f"\u274C Error creating log directory: {e}")
        exit()

    logging.basicConfig(
        filename = os.path.join(LOG_DIR, "errors.log"),
        level = logging.ERROR,
        format = "%(asctime)s - %(levelname)s - %(message)s",
    )
    
# ----------------------------------- #
# Ensure database and table existence
# ----------------------------------- #
def ensure_database_and_table():
    try:
        with connect_master() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sys.databases WHERE name = %s", (DB_NAME,))
                if cursor.fetchone():
                    print(f"\u2705 Database '{DB_NAME}' already exists.")
                else:
                    print(f"\u26A0 Database '{DB_NAME}' does not exist. Creating it...")
                    cursor.execute(f"CREATE DATABASE {DB_NAME}")
                    print(f"\u2705 Database '{DB_NAME}' created successfully!")
            connection.commit()
            connection.close()
            print("\u2705 Database part is done")

        with connect_to_database() as connection:
            with connection.cursor() as cursor:
            
            # Check if the 'usernames' table exists
                cursor.execute(
                """
                SELECT * FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = 'usernames'
                """
                )
                if cursor.fetchone():
                    print("\u2705 Table 'usernames' already exists.")
                    
                else:
                    print("\u26A0 Table 'usernames' does not exist. Creating it...")
                    cursor.execute(
                    """
                    CREATE TABLE usernames (
                        user_id_num INT IDENTITY(1,1) PRIMARY KEY,
                        username NVARCHAR(255) NOT NULL UNIQUE,
                        hashtag NVARCHAR(255) DEFAULT NULL,
                        profile_complete BIT NOT NULL DEFAULT 0,
                        posts_fetched BIT NOT NULL DEFAULT 0,
                        comments_fetched BIT NOT NULL DEFAULT 0,
                        user_processed BIT NOT NULL DEFAULT 0,
                        user_personality BIT NOT NULL DEFAULT 0
                    )
                    """
                )
                    print("\u2705 Table 'usernames' created successfully!")
                    
                connection.commit()
        
    except Exception as e:
        logging.error(f"Error ensuring database or table existence: {e}")
        print(f"\u274C Error ensuring database or table existence. Check logs for details. ", e)
        exit()

# ----------------------------------- #
# Load existing usernames from database
# ----------------------------------- #
def load_existing_usernames(connection):
    existing_usernames = set()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT username FROM usernames")
            rows = cursor.fetchall()
            for row in rows:
                existing_usernames.add(row[0])  # row[0] = username

        print(f"\U0001F4CB Loaded {len(existing_usernames)} existing usernames from the database.")
    except Exception as e:
        logging.error(f"Error loading existing usernames: {e}.")
        print(f"\u274C Error loading existing usernames: {e}.")
    return existing_usernames

# ----------------------------------- #
# Check user's existing from database or Nitter
# ----------------------------------- #
def check_user_existence(connection, username):
    
    existing_usernames = load_existing_usernames(connection)
    if username in existing_usernames:
        print(f"\u2705 Username '{username}' already exists in the database.")
        return True  
    
    print(f"Username '{username}' not in database. Checking Web...")
    
    try:
        url = f"{DOMAIN}{username}"
        response = requests.get(url, timeout=40)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        error_panel = soup.find("div", class_="error-panel")
        if error_panel and "User" in error_panel.text and "not found" in error_panel.text:
            print(f"\u274C User '{username}' not found on Web.")
            return False  

        print(f"\u2705 User '{username}' exists on Nitter. Adding to database...")
        save_username_to_db(connection, username)
        return True

    except Exception as e:
        time.sleep(random.uniform(3, 6))

    print("Too many failures. Could not verify user.")
    return False

# ----------------------------------- #
# Save new username to database
# ----------------------------------- #
def save_username_to_db(connection, username):
    try:
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO usernames (username) 
                    VALUES (%s)
                    """, (username,)
                    ) 
                connection.commit()
                print(f"\u2705 Username '{username}' saved to the database.")
                return True
            except pymssql.IntegrityError:
                print(f"Username '{username}' already exists. Skipping insert.")
                return False
    except Exception as e:
        logging.error(f"Error saving username to database: {e}.")
        print(f"\u274C Error saving username to database: {e}.")

# ----------------------------------- #
# Main function
# ----------------------------------- #
def main(username, connection):
    if not DB_HOST or not DB_NAME:
        print("\u274C Database configuration is missing.")
        return

    ensure_database_and_table()  

    user_exists = check_user_existence(connection, username)
    if user_exists:
        print(f"\u2705 Username '{username}' is now in the database.")
    else:
        print(f"\u274C Username '{username}' could not be found.")

    
    print("\u2705 Database connection closed.")


if __name__ == "__main__":
    main(username= input("username: "))
    #main(username= 'TakMesra')
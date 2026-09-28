import os
import requests
import pandas as pd
import random
import time
import logging
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
HASHTAGS = ["spacex"]
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DOMAIN = os.getenv("DOMAIN")
TARGET_COUNT = 5
MAX_PAGES = int(os.getenv("MAX_PAGES_PER_PERSON"))
LOG_DIR = "logs"

# ----------------------------------- #
# Connect to SQL Server Database
# ----------------------------------- #
def connect_to_database():
    try:
        connection = pymssql.connect(
            server = DB_HOST,
            database = DB_NAME
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
# Ensure 'usernames' table existence
# ----------------------------------- #
def ensure_table_exists(connection):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'usernames')
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
            """)
        connection.commit()
        
        print("\u2705 Table 'usernames' ensured.")
    except Exception as e:
        logging.error(f"Error ensuring table existence: {e}.")
        print(f"\u274C Error ensuring table existence: {e}.")
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
# Save new usernames to database
# ----------------------------------- #
def save_usernames_to_db(connection, new_usernames, hashtag):
    try:
        with connection.cursor() as cursor:
            for username in new_usernames:
                try:
                    cursor.execute(
                        """
                        INSERT INTO usernames (username)
                        VALUES (%s)
                        """,
                        (username)
                    )
                except pymssql.IntegrityError:
                    print(f"\u26A0 Skipping duplicate username: {username}")
                    continue    # Skip duplicates
        connection.commit()
        print(f"\u2705 {len(new_usernames)} new usernames saved to the database.")
    except Exception as e:
        logging.error(f"Error saving usernames to database: {e}.")
        print(f"\u274C Error saving usernames to database: {e}.")

# ----------------------------------- #
# Extract usernames from HTML page
# ----------------------------------- #
def extract_usernames(html, counter):
    soup = BeautifulSoup(html, "html.parser")
    usernames = []
    try:
        tweets = soup.find_all("div", class_="timeline-item")
        for tweet in tweets:
            if counter >= TARGET_COUNT:
                break
            if "show-more" in tweet.get("class", []):
                continue  # Ignore "Load Newest"
            username_tag = tweet.find("div", class_="fullname-and-username").find("a", class_="username")
            if username_tag:
                usernames.append(username_tag.text.strip("@"))
                counter += 1
    except Exception as e:
        logging.error(f"Error extracting usernames: {e}.")
        print(f"\u274C Error extracting usernames: {e}.")
    return usernames

# ----------------------------------- #
# Fetch usernames for a given hashtag
# ----------------------------------- #
def fetch_usernames_for_hashtag(connection, hashtag, existing_usernames):
    print(f"\U0001F50D Fetching usernames for hashtag: #{hashtag}...")

    base_url = f"{DOMAIN}search?f=tweets&q=%23{hashtag}"
    collected_usernames = []
    pages_count = 0
    MAX_RETRIES = 5
    retries = 0 
    while len(collected_usernames) < TARGET_COUNT and pages_count < MAX_PAGES and retries < MAX_RETRIES:
            try:
                response = requests.get(base_url, timeout=40)
                response.raise_for_status()
                print(f"\u2705 Successfully fetched data for #{hashtag}.")

                # "No item found" problem
                soup = BeautifulSoup(response.text, "html.parser")
                if soup.find("h2", class_="timeline-none"):
                    print(f"This #{hashtag} has no data.")
                    return None

                # Parse HTML and extract data
                usernames = extract_usernames(response.text, len(collected_usernames))
                new_usernames = [user for user in usernames if user not in existing_usernames]

                if new_usernames:
                    save_usernames_to_db(connection, new_usernames, hashtag)
                    collected_usernames.extend(new_usernames)
                    existing_usernames.update(new_usernames)

                if len(collected_usernames) >= TARGET_COUNT:
                    print(f"\u2705 Target count reached for #{hashtag}. Exiting ...")
                    return collected_usernames

                # Check for "Load More" button
                load_more = soup.find(lambda tag: tag.name == "div" and "show-more" in tag.get("class", []) and "timeline-item" not in tag.get("class", []))
                if load_more:
                    next_cursor = load_more.find("a")["href"]
                    base_url = f"{DOMAIN}search{next_cursor}"
                    print(f"\U0001F517 Next page URL: {base_url}")
                    
                else:
                    print(f"\u274C No Load More button found. Stopping requests for #{hashtag}.")
                    break 

                pages_count += 1
                print(f"\U0001F504 Processed page {pages_count} for #{hashtag}.")
                

            except requests.exceptions.Timeout:
                print(f"\u23F3 Timeout error for #{hashtag}. Retrying...")
                retries += 1
                time.sleep(random.uniform(3, 6))
           
            except requests.exceptions.RequestException as e:
                print(f"\u274C Request error for #{hashtag} :{e}. Retrying...")
                retries += 1
                time.sleep(random.uniform(3, 6))
                
            except Exception as e:
                print(f"\u274C Unexpected error for #{hashtag} :{e}. Retrying...")
                retries += 1
                time.sleep(random.uniform(3, 6))
        
    if retries >= MAX_RETRIES:
        print(f"\U0001F6A8 Too many failed requests ({retries}). Exiting ...")
        return 

# ----------------------------------- #
# Main function
# ----------------------------------- #
def main(connection):
    
    if not DB_HOST or not DB_NAME or not HASHTAGS:
        logging.error(f"Error: Database configuration is missing. Please check your .env file.")
        print("\u274C Error: Database configuration is missing. Please check your .env file.")
        return

    ensure_table_exists(connection)

    existing_usernames = load_existing_usernames(connection)

    # Process each hashtag for finding usernames
    for hashtag in HASHTAGS:
        fetch_usernames_for_hashtag(connection, hashtag, existing_usernames)

    connection.commit()
    print("\u2705 Database connection closed.")

if __name__ == "__main__":
    main(connect_to_database())

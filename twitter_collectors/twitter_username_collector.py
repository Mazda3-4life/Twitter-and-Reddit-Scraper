import os
import requests
import pandas as pd
import random
import time
import pymssql
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import logging

# ----------------------------------- #
# Load environment variables
# ----------------------------------- #
load_dotenv()

# ----------------------------------- #
# Constants and configurations
# ----------------------------------- #
PROXY_FILE = os.getenv("PROXY_FILE")
HASHTAGS = ["spacex"]
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
TARGET_COUNT = 3
MAX_PAGES = 50  
MAX_RETRIES_PER_PROXY = 3  
MAX_TOTAL_FAILURES = 10  
TRIED_PROXIES = set()
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
                        INSERT INTO usernames (username, hashtag, profile_complete, posts_fetched, comments_fetched, user_processed) 
                        VALUES (%s, %s, 0, 0, 0)
                        """,
                        (username, hashtag)
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
# Load proxy list
# ----------------------------------- #
def load_proxies(file_name):
    if not os.path.exists(file_name):
        print(f"\u274C Proxy file '{file_name}' does not exist. Please check the directory.")
        return None
    try:
        proxies_df = pd.read_csv(file_name)
        return proxies_df["Proxy Link"].dropna().tolist()
    except Exception as e:
        logging.error(f"Error loading proxies: {e}.")
        print(f"\u274C Error loading proxies: {e}.")
        return None

# ----------------------------------- #
# Select a random proxy
# ----------------------------------- #
def get_random_proxy(proxies):
    return random.choice(proxies)

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
def fetch_usernames_for_hashtag(connection, hashtag, proxies, existing_usernames):
    print(f"\U0001F50D Fetching usernames for hashtag: #{hashtag}...")

    base_url = f"https://nitter.privacydev.net/search?f=tweets&q=%23{hashtag}"
    collected_usernames = []
    pages_count = 0
    total_failures = 0  
    if not proxies:
        print("\u274C No proxies available. Exiting...")
        return

    while len(collected_usernames) < TARGET_COUNT and pages_count < MAX_PAGES:
        proxy = get_random_proxy(proxies)
        proxy_dict = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
        print(f"\u23F3 Using proxy: {proxy}")

        if len(TRIED_PROXIES) == len(proxies):
            print(f"\U0001F6A8 All proxies failed. Exiting...")
            exit()
        
        proxy = get_random_proxy(proxies)
        while proxy in TRIED_PROXIES:
            proxy = get_random_proxy(proxies)

        retries = 0  
        while retries < MAX_RETRIES_PER_PROXY:
            try:
                response = requests.get(base_url, proxies=proxy_dict, timeout=40)
                response.raise_for_status()
                print(f"\u2705 Successfully fetched data for #{hashtag} using proxy: {proxy}")

                # "No item found" problem
                soup = BeautifulSoup(response.text, "html.parser")
                if soup.find("h2", class_="timeline-none"):
                    print("This #{hashtag} has no data.")
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
                    return 

                # Check for "Load More" button
                load_more = soup.find(lambda tag: tag.name == "div" and "show-more" in tag.get("class", []) and "timeline-item" not in tag.get("class", []))
                if load_more:
                    next_cursor = load_more.find("a")["href"]
                    base_url = f"https://nitter.privacydev.net/search{next_cursor}"
                    print(f"\U0001F517 Next page URL: {base_url}")
                else:
                    print("\u274C No Load More button found. Stopping requests for #{hashtag}.")
                    break 

                pages_count += 1
                print(f"\U0001F504 Processed page {pages_count} for #{hashtag}.")
                break 

            except requests.exceptions.Timeout:
                print(f"\u23F3 Timeout error for #{hashtag} with proxy: {proxy}. Retrying ({retries+1}/{MAX_RETRIES_PER_PROXY})...")
                retries += 1
                time.sleep(random.uniform(3, 6))
            except requests.exceptions.ProxyError:
                print(f"\u274C Proxy error for #{hashtag} with proxy: {proxy}. Retrying ({retries+1}/{MAX_RETRIES_PER_PROXY})...")
                retries += 1
                time.sleep(random.uniform(3, 6))
            except requests.exceptions.RequestException as e:
                print(f"\u274C Request error for #{hashtag} with proxy: {proxy}: {e}. Retrying ({retries+1}/{MAX_RETRIES_PER_PROXY})...")
                retries += 1
                time.sleep(random.uniform(3, 6))
            except Exception as e:
                print(f"\u274C Unexpected error for #{hashtag} with proxy: {proxy}: {e}. Retrying ({retries+1}/{MAX_RETRIES_PER_PROXY})...")
                retries += 1
                time.sleep(random.uniform(3, 6))
        
        if retries >= MAX_RETRIES_PER_PROXY:    
            print(f"\u274C Proxy {proxy} failed after {MAX_RETRIES_PER_PROXY} attempts. Trying next proxy...")
            TRIED_PROXIES.add(proxy)

    if total_failures >= MAX_TOTAL_FAILURES:
        print(f"\U0001F6A8 Too many failed requests ({total_failures}). Exiting ...")
        return 

# ----------------------------------- #
# Main function
# ----------------------------------- #
def main():
    
    if not DB_HOST or not DB_NAME or not HASHTAGS:
        logging.error(f"Error: Database configuration is missing. Please check your .env file.")
        print("\u274C Error: Database configuration is missing. Please check your .env file.")
        return
    
    
    connection = connect_to_database()

    ensure_table_exists(connection)

    proxies = load_proxies(PROXY_FILE)
    if not proxies:
        logging.error(f"Error: No proxies available.")
        print("\u274C No proxies available at startup. Exiting...")
        return
    
    existing_usernames = load_existing_usernames(connection)

    # Process each hashtag for finding usernames
    for hashtag in HASHTAGS:
        fetch_usernames_for_hashtag(connection, hashtag, proxies, existing_usernames)

    connection.close()
    print("\u2705 Database connection closed.")

if __name__ == "__main__":
    main()

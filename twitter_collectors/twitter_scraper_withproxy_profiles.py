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
PROXY_FILE = os.getenv("PROXY_FILE")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
MAX_RETRIES_PER_PROXY = 2  
MAX_TOTAL_FAILURES = 10 
tried_proxies = set()
LOG_DIR = "logs"

# ----------------------------------- #
# Database connection
# ----------------------------------- #
def connect_to_database():
    try:
        connection = pymssql.connect(server = DB_HOST, database = DB_NAME)
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
# Ensure table exists
# ----------------------------------- #
def ensure_tables_exist(connection):
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'users')
                CREATE TABLE users (
                    user_id_num INT,
                    fullname NVARCHAR(255) NOT NULL,
                    username NVARCHAR(255) NOT NULL UNIQUE,
                    mbti_type VARCHAR(4) DEFAULT NULL,
                    bio NVARCHAR(MAX),
                    location NVARCHAR(255),
                    website NVARCHAR(255),
                    join_date NVARCHAR(255),
                    tweets INT,
                    followers INT,
                    following INT,
                    likes INT,
                    posts_status VARCHAR(255) NOT NULL DEFAULT 'Not processed',
                    comments_status VARCHAR(255) NOT NULL DEFAULT 'not processed'
                    FOREIGN KEY (user_id_num) REFERENCES usernames(user_id_num)
                )
                """
            )
        connection.commit()
        print("\u2705 Tables ensured.")
    except Exception as e:
        logging.error(f"Error ensuring tables exist: {e}.")
        print(f"\u274C Error ensuring tables exist: {e}")
        exit()

# ----------------------------------- #
# Load unprocessed usernames
# ----------------------------------- #
def load_unprocessed_usernames(connection):
    usernames = {}
    try:
        with connection.cursor(as_dict=True) as cursor:
            cursor.execute("SELECT user_id_num, username FROM usernames WHERE profile_complete = 0")
            for row in cursor.fetchall():
                usernames[row["username"]] = row["user_id_num"]
        print(f"\U0001F4CB Loaded {len(usernames)} unprocessed usernames from database.")
    except Exception as e:
        logging.error(f"Error loading usernames: {e}.")
        print(f"\u274C Error loading usernames: {e}")
    return usernames

# ----------------------------------- #
# Load valid proxies from a CSV file
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
        print(f"\u274C Error loading proxies: {e}")
        return None

# ----------------------------------- #
# Select a random proxy from the list
# ----------------------------------- #
def get_random_proxy(proxies):
    return random.choice(proxies)

# ----------------------------------- #
# Extract account information from the HTML content
# ----------------------------------- #
def extract_account_info(html, username):
    soup = BeautifulSoup(html, "html.parser")
    try:
        fullname = soup.find("a", class_="profile-card-fullname").text.strip()
        username = soup.find("a", class_="profile-card-username").text.strip()
        bio = soup.find("div", class_="profile-bio").text.strip() if soup.find("div", class_="profile-bio") else "N/A"
        location = soup.find("div", class_="profile-location").text.strip() if soup.find("div", class_="profile-location") else "N/A"
        website = soup.find("div", class_="profile-website").find("a").text.strip() if soup.find("div", class_="profile-website") else "N/A"
        join_date = soup.find("div", class_="profile-joindate").text.strip()

        stats = soup.find("ul", class_="profile-statlist")
        
        def clean_number(value):
            """Remove commas from numbers and convert to int (default to 0 if empty)."""
            return int(value.replace(',', '')) if value and value.replace(',', '').isdigit() else 0

        tweets = clean_number(stats.find("li", class_="posts").find("span", class_="profile-stat-num").text.strip()) if stats else 0
        followers = clean_number(stats.find("li", class_="followers").find("span", class_="profile-stat-num").text.strip()) if stats else 0
        following = clean_number(stats.find("li", class_="following").find("span", class_="profile-stat-num").text.strip()) if stats else 0
        likes = clean_number(stats.find("li", class_="likes").find("span", class_="profile-stat-num").text.strip()) if stats else 0

        return {
            "fullname": fullname,
            "username": username,
            "bio": bio,
            "location": location,
            "website": website,
            "join_date": join_date,
            "tweets": tweets,
            "followers": followers,
            "following": following,
            "likes": likes,
        }
    except Exception as e:
        logging.error(f"Error extracting account info for @{username}: {e}.")
        print(f"\u274C Error extracting account info for @{username}: {e}")
        return None

# ----------------------------------- #
# Fetch account data with proxy support
# ----------------------------------- #
def fetch_account_data(username, proxies, proxy_file):
    print(f"\U0001F50D Fetching account data for user: {username}...")
    total_failures = 0  
    
    if not proxies:
        print("\u274C No proxies available. Exiting...")
        return
    
    while total_failures < MAX_TOTAL_FAILURES:
        
        if len(tried_proxies) == len(proxies):
            print(f"\U0001F6A8 All proxies failed. Exiting...")
            exit()
        
        proxy = get_random_proxy(proxies)
        while proxy in tried_proxies:
            proxy = get_random_proxy(proxies)
        proxy_dict = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
        print(f"\u23F3 Using proxy: {proxy}")
                
        retries = 0  
        while retries < MAX_RETRIES_PER_PROXY:
            try:
                url = f"https://nitter.privacydev.net/{username}"
                response = requests.get(url, proxies=proxy_dict, timeout=40)
                response.raise_for_status()
                print(f"\u2705 Successfully fetched data for @{username} using proxy: {proxy}")
                return extract_account_info(response.text, username)

            except requests.exceptions.Timeout:
                print(f"\u23F3 Timeout error for @{username} with proxy: {proxy}. Retrying ({retries+1}/{MAX_RETRIES_PER_PROXY})...")
                retries += 1
                time.sleep(random.uniform(3, 6))

            except requests.exceptions.ProxyError:
                print(f"\u274C Proxy error for @{username} with proxy: {proxy}. Retrying ({retries+1}/{MAX_RETRIES_PER_PROXY})...")
                retries += 1
                time.sleep(random.uniform(3, 6))

            except requests.exceptions.RequestException as e:
                print(f"\u274C Request error for @{username} with proxy: {proxy}: {e}. Retrying ({retries+1}/{MAX_RETRIES_PER_PROXY})...")
                retries += 1
                time.sleep(random.uniform(3, 6))

            except Exception as e:
                print(f"\u274C Unexpected error for @{username} with proxy: {proxy}: {e}. Retrying ({retries+1}/{MAX_RETRIES_PER_PROXY})...")
                retries += 1
                time.sleep(random.uniform(3, 6))

            
        if retries >= MAX_RETRIES_PER_PROXY:    
            print(f"\u274C Proxy {proxy} failed after {MAX_RETRIES_PER_PROXY} attempts. Trying next proxy...")
            total_failures += 1
            tried_proxies.add(proxy)

        time.sleep(random.uniform(6, 10)) 
    if total_failures >= MAX_TOTAL_FAILURES:
        print(f"\U0001F6A8 Too many failed requests ({total_failures}). Exiting ...")
        return 
    
# ----------------------------------- #
# Insert data into database
# ----------------------------------- #
def insert_account_data(connection, user_id, data):
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (user_id_num, fullname, username, bio, location, website, join_date, tweets, followers, following, likes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, data["fullname"], data["username"], data["bio"], data["location"],
                 data["website"], data["join_date"], data["tweets"], data["followers"],
                 data["following"], data["likes"])
            )
        connection.commit()
        print(f"\u2705 Account data saved for {data['username']}.")
        return 1
    except Exception as e:
        logging.error(f"Error inserting data for{data['username']}: {e}.")
        print(f"\u274C Error inserting data for {data['username']}: {e}")
        return 0

# ----------------------------------- #
# Update profile status in database
# ----------------------------------- #
def update_profile_status(connection, user_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE usernames SET profile_complete = 1 WHERE user_id_num = %s", (user_id,))
        connection.commit()
        print(f"\u2705 Profile status updated for user_id: {user_id}")
    except Exception as e:
        logging.error(f"Error updating profile status for user_id {user_id}: {e}.")
        print(f"\u274C Error updating profile status for user_id {user_id}: {e}")

# ----------------------------------- #
# Main function
# ----------------------------------- #
def main():
    
    if not DB_HOST or not DB_NAME:
        print("\u274C Error: Database configuration is missing. Please check your .env file.")
        return

    connection = connect_to_database()

    ensure_tables_exist(connection)

    usernames = load_unprocessed_usernames(connection)
    if not usernames:
        print("\u2705 No unprocessed usernames found. Exiting...")
        return

    proxies = load_proxies(PROXY_FILE)
    if not proxies:
        print("\u274C No proxies available at startup. Exiting...")
        return

    # Process each unprocessed username
    for username, user_id in usernames.items():
        print(f"\U0001F50D Processing @{username} (User ID: {user_id})")

        # Fetch account data using proxies
        account_data = fetch_account_data(username, proxies, PROXY_FILE)
        if account_data:
            # Insert account data into the database
            inserted = insert_account_data(connection, user_id, account_data)
            if inserted:
                # Update process status
                update_profile_status(connection, user_id)
        else:
            print(f"\u26A0 Skipping @{username} due to fetching errors.")

    # Close database connection
    connection.close()
    print("\u2705 Database connection closed.")

# Execute the program
if __name__ == "__main__":
    main()

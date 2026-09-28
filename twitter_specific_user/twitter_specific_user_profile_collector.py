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
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DOMAIN = os.getenv("DOMAIN")
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
def get_user_id_if_unprocessed(connection, username):
    try:
        with connection.cursor(as_dict=True) as cursor:
            cursor.execute(
                "SELECT user_id_num FROM usernames WHERE username = %s AND profile_complete = 0", 
                (username,)
            )
            row = cursor.fetchone()
            if row:
                print(f"\u2705 Found unprocessed username: {username}")
                return row["user_id_num"]
            else:
                print(f"Username {username} already processed or not found.")
                return None
    except Exception as e:
        logging.error(f"Error checking username {username}: {e}")
        print(f"\u274C Error checking username {username}: {e}")
        return None

# ----------------------------------- #
# Extract account information from the HTML content
# ----------------------------------- #
def extract_account_info(html, username):
    soup = BeautifulSoup(html, "html.parser")
    try:
        fullname = soup.find("a", class_="profile-card-fullname").text.strip()
        
        extracted_username = soup.find("a", class_="profile-card-username").text.strip()
        username = username.strip("@")

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
# Fetch account data 
# ----------------------------------- #
def fetch_account_data(username):
    print(f"\U0001F50D Fetching account data for user: {username}...")
    MAX_RETRIES = 5  
    retries = 0
    while retries < MAX_RETRIES:
        try:
            url = f"{DOMAIN}{username}"
            response = requests.get(url, timeout=40)
            response.raise_for_status()
            print(f"\u2705 Successfully fetched data for @{username}.")
            return extract_account_info(response.text, username)

        except requests.exceptions.Timeout:
            print(f"\u23F3 Timeout error for @{username}...")
            retries += 1
            time.sleep(random.uniform(3, 6))

        except requests.exceptions.RequestException as e:
            print(f"\u274C Request error for @{username}...")
            retries += 1
            time.sleep(random.uniform(3, 6))

        except Exception as e:
            print(f"\u274C Unexpected error for @{username}...")
            retries += 1
            time.sleep(random.uniform(3, 6))
    
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
def main(username, connection):
    if not DB_HOST or not DB_NAME:
        print("\u274C Error: Database configuration is missing. Please check your .env file.")
        return
    #print(1)
    
    ensure_tables_exist(connection)
    #print(2)
    

    user_id = get_user_id_if_unprocessed(connection, username)
    if not user_id:
        print("\u2705 No unprocessed usernames found. Exiting...")
        connection.commit()
        return
    #print(3)

    print(f"Processing @{username} (User ID: {user_id})")

    # Fetch account data
    account_data = fetch_account_data(username)
    if account_data:
        if insert_account_data(connection, user_id, account_data):
            update_profile_status(connection, user_id)
    else:
        print(f"\u274C Skipping @{username} due to fetching errors.")

    connection.commit()
    print("\u2705 Database connection closed.")

#---------------------------------------
# Execute the program
#---------------------------------------
if __name__ == "__main__":
    username = input("Enter your username:").strip()
    main(username, connection= connect_to_database())
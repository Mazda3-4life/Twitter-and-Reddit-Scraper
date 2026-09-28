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
TARGET_COUNT = 100
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
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'comments')
                CREATE TABLE comments (
                    user_id_num INT,
                    replying_to NVARCHAR(50),
                    comment_text NVARCHAR(MAX),
                    FOREIGN KEY (user_id_num) REFERENCES usernames(user_id_num)
                )
                """
            )
        connection.commit()
        print("\u2705 Table 'comments' ensured.")
    except Exception as e:
        logging.error(f"Error ensuring tables exist: {e}.")
        print(f"\u274C Error ensuring tables exist: {e}")
        exit()

# ----------------------------------- #
# Load unprocessed username
# ----------------------------------- #
def get_user_id_if_unprocessed_comments(connection, username):
    try:
        with connection.cursor(as_dict=True) as cursor:
            cursor.execute(
                "SELECT user_id_num FROM usernames WHERE username = %s AND comments_fetched = 0", 
                (username,)
            )
            row = cursor.fetchone()


        if row:
            print(f"\u2705 Found username {username} with comments_fetched=0")
            return row["user_id_num"]
        else:
            print(f"Username {username} either already processed or not found.")
            return None
        


    except Exception as e:
        logging.error(f"Error checking username {username}: {e}")
        print(f"\u274C Error checking username {username}: {e}")
        return None
    

# ----------------------------------- #
# Extract replies from the HTML content
# ----------------------------------- #
def extract_replies(html, username, counters):
    soup = BeautifulSoup(html, "html.parser")
    tweets = soup.find_all("div", class_="timeline-item")
    extracted_replies = {"text": [], "replying_to": []}

    for tweet in tweets:
        if counters >= TARGET_COUNT:
            break

        # Ignore "Load newest"
        if "timeline-item" in tweet.get("class", []) and "show-more" in tweet.get("class", []):
            continue

        # Identify headers and content
        replying_to = tweet.find("div", class_="replying-to")
        tweet_content = tweet.find("div", class_="tweet-content")
        tweet_text = tweet_content.text.strip() if tweet_content else ""
        
        # Extract username of the author
        tweet_header = tweet.find("div", class_="tweet-header")
        user_info = tweet_header.find("div", class_="fullname-and-username") if tweet_header else None
        tweet_username = user_info.find("a", class_="username").text.strip() if user_info else None

        # Identify replies
        if replying_to and tweet_username == f"@{username}":
            reply_to_user = replying_to.find("a").text.strip() if replying_to.find("a") else None
            counters += 1
            extracted_replies["text"].append(tweet_text)
            extracted_replies["replying_to"].append(reply_to_user)

    return extracted_replies

# ----------------------------------- #
# Fetch replies with proxy support
# ----------------------------------- #
def fetch_replies(username, user_id, connection):
    print(f"\U0001F50D Fetching replies for user: {username}...")
    url = f"{DOMAIN}{username}/with_replies"
    all_data = {"text": [], "replying_to": []}
    
    retries = 0
    MAX_RETRIES = 5
    while len(all_data["replying_to"]) < TARGET_COUNT and retries < MAX_RETRIES:
        try:
            response = requests.get(url, timeout=40)
            response.raise_for_status()
            print(f"\u2705 Successfully fetched data from {url}.")

            # "No item found" problem
            soup = BeautifulSoup(response.text, "html.parser")
            if soup.find("h2", class_="timeline-none"):
                print("This user has no reply.")
                update_profile_status(connection, user_id)

                try:
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE users SET comments_status = 'No comment' WHERE user_id_num = %s", (user_id,))
                    connection.commit()
                    print(f"\u2705 comments status column in users table updated for user_id: {user_id}")
                except Exception as e:
                    print(f"\u274C Error updating comments status column in users table for user_id {user_id}: {e}")
                return None

            # Parse HTML and extract data
            extracted_data = extract_replies(response.text, username, len(all_data["replying_to"]))
            all_data["text"] += extracted_data["text"]
            all_data["replying_to"] += extracted_data["replying_to"]
            time.sleep(2)

            if len(all_data["replying_to"]) >= TARGET_COUNT:
                print("\U0001F6A8 Reached 100 replies for user_ID:{user_id}, username: {username}. Stopping...")
                return all_data

            # Check for "Load More" button
            load_more = soup.find(lambda tag: tag.name == "div" and "show-more" in tag.get("class", []) and "timeline-item" not in tag.get("class", []))
            if load_more:
                next_cursor = load_more.find("a")["href"]
                print(f"\u2705 Next Load More URL: {next_cursor}")
                url = f"{DOMAIN}/{username}/with_replies?{next_cursor.split('?')[-1]}"
            else:
                print("\u274C No Load More button found. Stopping requests.")
                return all_data

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
    
    return all_data

# ----------------------------------- #
# Insert replies into database
# ----------------------------------- #
def insert_replies_to_db(connection, user_id, replies):
    try:
        with connection.cursor() as cursor:
            #print(replies)
            for text, replying_to in zip(replies['text'], replies["replying_to"]):
                cursor.execute(
                    """
                    INSERT INTO comments (user_id_num, replying_to, comment_text) 
                    VALUES (%s, %s, %s)
                    """,
                    (user_id,  replying_to, text)
                )
        connection.commit()
        print(f"\u2705 {len(replies)} replies saved for user_ID:{user_id} in database.")
    except Exception as e:
        logging.error(f"Error saving for user_ID {user_id} in database: {e}.")
        print(f"\u274C Error saving for user_ID {user_id} in database: {e}")


# ----------------------------------- #
# Update profile status in database
# ----------------------------------- #
def update_profile_status(connection, user_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE usernames SET comments_fetched = 1 WHERE user_id_num = %s", (user_id,))
        connection.commit()
        print(f"\u2705 Profile status updated for user_id: {user_id}")
    except Exception as e:
        logging.error(f"Error updating profile status for user_id {user_id}: {e}.")
        print(f"\u274C Error updating profile status for user_id {user_id}: {e}")

# ----------------------------------- #
# Update comments status column in users table
# ----------------------------------- #
def update_comments_column_status(connection, user_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE users SET comments_status = 'sucessfully processed' WHERE user_id_num = %s", (user_id,))
        connection.commit()
        print(f"\u2705 comments status column in users table updated for user_id: {user_id}")
    except Exception as e:
        logging.error(f"Error updating comments status column in users table for user_id {user_id}: {e}.")
        print(f"\u274C Error updating comments status column in users table for user_id {user_id}: {e}")

# ----------------------------------- #
# Main function
# ----------------------------------- #
def main(username, connection):
    if not DB_HOST or not DB_NAME:
        print("\u274C Error: Database configuration is missing.")
        return

    #print("\u2705 P1")
    
    ensure_tables_exist(connection)

    #print("\u2705 P2")

    user_id = get_user_id_if_unprocessed_comments(connection, username)
    if not user_id:
        print("\u2705 No unprocessed comments for this username.")
        connection.close()
        return

    #print("\u2705 P3")

    print(f"Processing comments for @{username} (User ID: {user_id})")

    # Fetch replies
    data = fetch_replies(username, user_id, connection)
    #print("\u2705 P4.1")
    if data:
        insert_replies_to_db(connection, user_id, data)
        #print("\u2705 P4.2")
        update_profile_status(connection, user_id)
        #print("\u2705 P4.3")
        update_comments_column_status(connection, user_id)
        #print("\u2705 P4.4")
    else:
        print(f"Skipping @{username} due to fetching errors.")
        
    #print("\u2705 P4")

    connection.commit()
    print("\u2705 Database connection closed.")
    
    #print("\u2705 P5")

# ----------------------------------- #
# Execute main function
# ----------------------------------- #
if __name__ == "__main__":
    username = input("Enter your username:").strip()
    main(username)
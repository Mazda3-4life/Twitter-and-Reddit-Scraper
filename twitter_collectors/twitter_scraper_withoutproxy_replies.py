import os
import requests
import pandas as pd
import random
import time
import pymssql
import logging
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ----------------------------------- #
# Load environment variables
# ----------------------------------- #
load_dotenv()

# ----------------------------------- #
# Constants and configurations
# ----------------------------------- #
TARGET_COUNT = 100
MAX_PAGES = int(os.getenv("MAX_PAGES_PER_PERSON"))
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
# Load unprocessed usernames(comments_fetched = 0)
# ----------------------------------- #
def load_unprocessed_usernames(connection):
    usernames = {}
    try:
        with connection.cursor(as_dict=True) as cursor:
            cursor.execute("SELECT user_id_num, username FROM usernames WHERE comments_fetched = 0")
            for row in cursor.fetchall():
                usernames[row["username"]] = row["user_id_num"]
        print(f"\U0001F4CB Loaded {len(usernames)} unprocessed usernames from database.")
    except Exception as e:
        logging.error(f"Error loading usernames: {e}.")
        print(f"\u274C Error loading usernames: {e}")
    return usernames

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
    
    page = 1
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
                print(f"\U0001F6A8 Reached {len(all_data["replying_to"])} replies for user_ID:{user_id}, username: {username}. Stopping...")
                return all_data

            # Check for "Load More" button
            load_more = soup.find(lambda tag: tag.name == "div" and "show-more" in tag.get("class", []) and "timeline-item" not in tag.get("class", []))
            if load_more:
                next_cursor = load_more.find("a")["href"]
                print(f"\u2705 Next Load More URL: {next_cursor}")
                url = f"{DOMAIN}{username}/with_replies?{next_cursor.split('?')[-1]}"
                
                page = page + 1
                print(f"Currently on page {page}")
                print(f"Collected {len(all_data["replying_to"])} replies so far")
                
                if len(all_data["replying_to"]) >= TARGET_COUNT or MAX_PAGES <= page:
                    print(f"\U0001F6A8 Reached {len(all_data["replying_to"])} replies for user_ID:{user_id}, username: {username}. Stopping...")
                    return all_data
            else:
                print("\u274C No Load More button found. Stopping requests.")
                return all_data

        except requests.exceptions.Timeout:
            print(f"\u23F3 Timeout error for @{username}. Retrying...")
            retries += 1
            time.sleep(random.uniform(3, 6))
       
        except requests.exceptions.RequestException as e:
            print(f"\u274C Request error for @{username} :{e}. Retrying...")
            retries += 1
            time.sleep(random.uniform(3, 6))

        except Exception as e:
            print(f"\u274C Unexpected error for @{username} :{e}. Retrying...")
            retries += 1
            time.sleep(random.uniform(3, 6))
        
    if retries >= MAX_RETRIES:
        print(f"\U0001F6A8 Too many failed requests ({retries}). Exiting ...")
        return   

    return all_data

# ----------------------------------- #
# Insert replies into database
# ----------------------------------- #
def insert_replies_to_db(connection, user_id, replies):
    try:
        with connection.cursor() as cursor:
            for replying_to, text in zip(replies["replying_to"], replies["text"]):
                cursor.execute(
                    """
                    INSERT INTO comments (user_id_num, replying_to, comment_text) 
                    VALUES (%s, %s, %s)
                    """,
                    (user_id,  replying_to, text)
                )
        connection.commit()
        print(f"\u2705 {len(replies["replying_to"])} replies saved for user_ID:{user_id} in database.")
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
def main(connection):

    if not DB_HOST or not DB_NAME:
        print("\u274C Error: Database configuration is missing. Please check your .env file.")
        return

    ensure_tables_exist(connection)
    
    usernames = load_unprocessed_usernames(connection)
    if not usernames:
        print("\u2705 No unprocessed usernames found. Exiting...")
        return

    for username, user_id in usernames.items():
        print(f"\U0001F50D Processing @{username} (User ID: {user_id})")

        # Fetch replies data
        data = fetch_replies(username, user_id, connection)
        
        if data:
            insert_replies_to_db(connection, user_id, data)
            
            # Update process status
            update_profile_status(connection, user_id)
            update_comments_column_status(connection, user_id)
                
        else:
            print(f"\u26A0 Skipping @{username} due to fetching errors.")


    connection.commit()
    #print("\u2705 Database connection closed.")

# Execute the program
if __name__ == "__main__":
    main()

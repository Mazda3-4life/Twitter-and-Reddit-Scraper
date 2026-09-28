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
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'tweets')
                CREATE TABLE tweets (
                    user_id_num INT,
                    tweet_type NVARCHAR(50),
                    tweet_text NVARCHAR(MAX),
                    FOREIGN KEY (user_id_num) REFERENCES usernames(user_id_num)
                )
                """
            )
        connection.commit()
        print("\u2705 Table 'tweets' ensured.")
    except Exception as e:
        logging.error(f"Error ensuring tables exist: {e}.")
        print(f"\u274C Error ensuring tables exist: {e}.")
        exit()

# ----------------------------------- #
# Load unprocessed usernames(tweets_fetched = 0)
# ----------------------------------- #
def load_unprocessed_usernames(connection):
    usernames = {}
    try:
        with connection.cursor(as_dict=True) as cursor:
            cursor.execute("SELECT user_id_num, username FROM usernames WHERE posts_fetched = 0")
            for row in cursor.fetchall():
                usernames[row["username"]] = row["user_id_num"]
        print(f"\U0001F4CB Loaded {len(usernames)} unprocessed usernames from database.")
    except Exception as e:
        logging.error(f"Error loading usernames: {e}.")
        print(f"\u274C Error loading usernames: {e}")
    return usernames

# ----------------------------------- #
# Extract tweets and retweets from the HTML content
# ----------------------------------- #
def extract_tweets(html, username, counters):
    soup = BeautifulSoup(html, "html.parser")
    tweets = soup.find_all("div", class_="timeline-item")
    extracted_tweets = {"tweets": [], "retweets_with_comments": []}
    
    for tweet in tweets:
        if counters["tweets"] + counters["retweets_with_comments"] >= TARGET_COUNT:
            break

        # Ignore "Load newest"
        if "timeline-item" in tweet.get("class", []) and "show-more" in tweet.get("class", []):
            continue

        # Identify headers and content
        retweet_header = tweet.find("div", class_="retweet-header")
        tweet_content = tweet.find("div", class_="tweet-content")
        tweet_text = tweet_content.text.strip() if tweet_content else ""

        # Extract username of the author
        tweet_header = tweet.find("div", class_="tweet-header")
        user_info = tweet_header.find("div", class_="fullname-and-username")
        tweet_username = user_info.find("a", class_="username").text.strip()

        # Categorize tweets based on conditions
        if retweet_header:
            if tweet_username == f"@{username}" and tweet_text:
                # Retweet with comment
                counters["retweets_with_comments"] += 1
                extracted_tweets["retweets_with_comments"].append(tweet.text.strip())
        elif not retweet_header and tweet_username == f"@{username}":
            # Original tweet
            counters["tweets"] += 1
            extracted_tweets["tweets"].append(tweet.text.strip())
    
        if counters["tweets"] + counters["retweets_with_comments"] >= TARGET_COUNT:
                break
    return extracted_tweets

# ----------------------------------- #
# Fetch tweets and retweets with proxy support
# ----------------------------------- #
def fetch_tweets(username, user_id, connection):
    print(f"\U0001F50D Fetching tweets for user: {username}...")
    url = f"{DOMAIN}{username}"
    counters = {"tweets": 0, "retweets_with_comments": 0}
    all_data = {"tweets": [], "retweets_with_comments": []}
    
    page = 1
    MAX_RETRIES = 5
    retries = 0
    
    while counters["tweets"] + counters["retweets_with_comments"] < TARGET_COUNT and retries < MAX_RETRIES:    
        try:
            response = requests.get(url, timeout=40)
            response.raise_for_status()
            print(f"\u2705 Successfully fetched data from {url}.")
            
            # "No item found" problem
            soup = BeautifulSoup(response.text, "html.parser")
            if soup.find("h2", class_="timeline-none"):
                print("This user has no tweet.")
                update_profile_status(connection, user_id)
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE users SET posts_status = 'No tweet' WHERE user_id_num = %s", (user_id,))
                    connection.commit()
                    print(f"\u2705 posts status column in users table updated for user_id: {user_id}")
                except Exception as e:
                    logging.error(f"Error updating posts status column in users table for user_id {user_id}: {e}.")
                    print(f"\u274C Error updating posts status column in users table for user_id {user_id}: {e}")
                return None
            
            # Parse HTML and extract data
            extracted_data = extract_tweets(response.text, username, counters)
            all_data["tweets"] += extracted_data["tweets"]
            all_data["retweets_with_comments"] += extracted_data["retweets_with_comments"]
            #time.sleep(2)

            if counters["tweets"] + counters["retweets_with_comments"] >= TARGET_COUNT:
                print(f"\U0001F6A8 Reached {counters["tweets"] + counters["retweets_with_comments"]} tweets for user_ID:{user_id}, username: {username}. Stopping...")
                return all_data
            
            # Check for "Load More" button
            load_more = soup.find(lambda tag: tag.name == "div" and "show-more" in tag.get("class", []) and "timeline-item" not in tag.get("class", []))
            if load_more:
                next_cursor = load_more.find("a")["href"]
                print(f"\U0001F517 Next Load More URL: {next_cursor}")
                url = f"{DOMAIN}{username}?{next_cursor.split('?')[-1]}"
                
                page = page +1
                print(f"Collected {counters["tweets"] + counters["retweets_with_comments"]} tweets so far")
                print(f"Currently on page {page}")
                
                if counters["tweets"] + counters["retweets_with_comments"] >= TARGET_COUNT or page > MAX_PAGES:
                    print(f"\U0001F6A8 Reached {counters["tweets"] + counters["retweets_with_comments"]} tweets for user_ID:{user_id}, username: {username}. Stopping...")
                    return all_data
            else:
                print("\u274C No Load More button found. Stopping requests.")
                return all_data

        except requests.exceptions.Timeout:
            print(f"\u23F3 Timeout error for @{username} : Retrying...")
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
# Insert tweets into database
# ----------------------------------- #
def insert_tweets_to_db(connection, user_id, tweets, tweet_type):
    try:
        with connection.cursor() as cursor:
            for tweet in tweets:
                cursor.execute(
                    """
                    INSERT INTO tweets (user_id_num, tweet_type,tweet_text) 
                    VALUES (%s, %s, %s)
                    """,
                    (user_id, tweet_type, tweet)
                )
                #print(tweet)
        connection.commit()
        print(f"\u2705 {len(tweets)} {tweet_type}s saved for user_ID: {user_id} in database.")
    except Exception as e:
        logging.error(f"Error saving{tweet_type}s for user_ID: {user_id} in database: {e}.")
        print(f"\u274C Error saving {tweet_type}s  for user_ID: {user_id} in database: {e}")

# ----------------------------------- #
# Update profile status in database
# ----------------------------------- #
def update_profile_status(connection, user_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE usernames SET posts_fetched = 1 WHERE user_id_num = %s", (user_id,))
        connection.commit()
        print(f"\u2705 Profile status updated for user_id: {user_id}")
    except Exception as e:
        print(f"\u274C Error updating profile status for user_id {user_id}: {e}")

# ----------------------------------- #
# Update posts status column in users table
# ----------------------------------- #
def update_posts_column_status(connection, user_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE users SET posts_status = 'sucessfully processed' WHERE user_id_num = %s", (user_id,))
        connection.commit()
        print(f"\u2705 posts status column in users table updated for user_id: {user_id}")
    except Exception as e:
        logging.error(f"Error updating posts status column in user table for user_id {user_id}: {e}.")
        print(f"\u274C Error updating posts status column in users table for user_id {user_id}: {e}")

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

        # Fetch tweets data using proxies
        data = fetch_tweets(username, user_id, connection)
        if data:
            insert_tweets_to_db(connection, user_id, data["tweets"], "tweet")
            insert_tweets_to_db(connection, user_id, data["retweets_with_comments"], "retweet_with_comment")

            # update process status
            update_profile_status(connection, user_id)
            update_posts_column_status(connection, user_id)
            
        else:
            print(f"\u26A0 Skipping @{username} due to fetching errors.")

    connection.commit()
    print("\u2705 Database connection closed.")

# Execute the program
if __name__ == "__main__":
    main(connect_to_database())

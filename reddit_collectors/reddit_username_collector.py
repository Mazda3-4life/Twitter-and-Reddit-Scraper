import os
import logging
import praw
import pymssql
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
LOG_DIR = "logs"

# ----------------------------------- #
# Connect to Reddit
# ----------------------------------- #
def initialize_reddit_client():
    try:
        reddit = praw.Reddit(
            client_id = os.getenv("CLIENT_ID"),
            client_secret = os.getenv("CLIENT_SECRET"),
            user_agent = os.getenv("USER_AGENT")
        )
        print("\u2705 Connected to Reddit API successfully!")
        return reddit
    except Exception as e:
        print(f"\u274C Error initializing Reddit client: {e}")
        exit()

# ----------------------------------- #
# Connect to DataBase
# ----------------------------------- #
def connect_master():
    try:
        conn = pymssql.connect(server=DB_HOST, database="master")
        conn.autocommit(True)
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
# Ensure database and table existence
# ----------------------------------- #
def ensure_reddit_database():
    try:
        with connect_master() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sys.databases WHERE name = %s", (DB_NAME,))
                if cursor.fetchone():
                    print(f"\u2705 Database '{DB_NAME}' already exists.")
                    flag =False
                else:
                    print(f"\u26A0 Database '{DB_NAME}' does not exist. Creating it...")
                    
                    cursor.execute(f"CREATE DATABASE {DB_NAME}")
                    print(f"\u2705 Database '{DB_NAME}' created successfully!")
                    
    except Exception as e:
        logging.error(f"Error ensuring database existence: {e}")
        print(f"\u274C Error ensuring database existence. Check logs for details.", e)
        exit()


def ensure_table():
    try:
        with connect_master() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sys.databases WHERE name = %s", (DB_NAME,))
                if cursor.fetchone():
                    print(f"\u2705 Database '{DB_NAME}' already exists.")
                    flag =False
                else:
                    print(f"\u26A0 Database '{DB_NAME}' does not exist. Creating it...")
                    
                    cursor.execute(f"CREATE DATABASE {DB_NAME}")
                    print(f"\u2705 Database '{DB_NAME}' created successfully!")

            
        #print("P2.1")
        with connect_to_database() as connection:
            #print("P2.2")
            with connection.cursor() as cursor:
            
            # Check if the 'usernames' table exists
                cursor.execute(
                """
                SELECT * FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = 'usernames'
                """
                )
                #print("P2.3")
                if cursor.fetchone():
                    print("\u2705 Table 'usernames' already exists.")
                else:
                    print("\u26A0 Table 'usernames' does not exist. Creating it...")
                    cursor.execute(
                    """
                    CREATE TABLE usernames (
                        user_id_num INT IDENTITY(1,1) PRIMARY KEY,
                        username NVARCHAR(255) NOT NULL UNIQUE,
                        profile_complete BIT NOT NULL DEFAULT 0,
                        posts_fetched BIT NOT NULL DEFAULT 0,
                        comments_fetched BIT NOT NULL DEFAULT 0,
                        user_subreddit_profile_complete BIT NOT NULL DEFAULT 0,
	                    user_trophies_complete BIT NOT NULL DEFAULT 0,
                        user_processed BIT NOT NULL DEFAULT 0,
                        user_personality BIT NOT NULL DEFAULT 0
                    )
                    """
                    )
                    print("\u2705 Table 'usernames' created successfully!")
                
                connection.commit()
                
    except Exception as e:
        logging.error(f"Error ensuring table existence: {e}")
        print(f"\u274C Error ensuring table existence. Check logs for details.", e)
        exit()

# ----------------------------------- #
# Load existing usernames from the database
# ----------------------------------- #
def load_existing_usernames(connection):
    existing_usernames = set()
    current_id = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT user_id_num, username FROM usernames")
            rows = cursor.fetchall()
            for user_id_num, username in rows:
                existing_usernames.add(username)
                current_id = max(current_id, user_id_num)

        # Print loaded usernames
        print(f"Existing usernames: {len(existing_usernames)}")

        print(f"\U0001F4CB Loaded {len(existing_usernames)} existing usernames from the database.")
    except Exception as e:
        logging.error(f"Error loading existing usernames: {e}")
        print(f"\u274C Error loading existing usernames. Check logs for details.", e)
    return existing_usernames, current_id

# ----------------------------------- #
# Fetch random usernames from Reddit
# ----------------------------------- #
def fetch_random_usernames(reddit, existing_usernames, limit=50):
    random_users = []
    try:
        for submission in reddit.subreddit("all").hot(limit=500):
            if submission.author and submission.author.name not in existing_usernames:
                if submission.author.name not in random_users:
                    random_users.append(submission.author.name)
            if len(random_users) >= limit:
                break
        print(f"\U0001F50D Fetched {len(random_users)} random usernames from Reddit.")
    except Exception as e:
        logging.error(f"Error fetching random usernames: {e}")
        print(f"\u274C Error fetching random usernames. Check logs for details.")
    return random_users

# ----------------------------------- #
# Insert new usernames into the database
# ----------------------------------- #
def insert_usernames(connection, usernames, existing_usernames, current_id):
    try:
        with connection.cursor() as cursor:
            for username in usernames:
                if username in existing_usernames:
                    print(f"Skipping {len(username)} existing username")
                    continue

                current_id += 1
                print(f"Inserting username: {username}, with ID: {current_id}")  # Debug line
                try:
                    cursor.execute(
                        "INSERT INTO usernames (username) VALUES (%s)",
                        (username)
                    )
                except pymssql.IntegrityError:
                    logging.warning(f"Duplicate username detected: {username}")
                    print(f"\u26A0 Skipping duplicate username: {username}")
                else:
                    existing_usernames.add(username)  # Update the set with new username
            connection.commit()
        print(f"\u2705 Added {len(usernames)} new usernames to the database.")
    except Exception as e:
        logging.error(f"Error inserting usernames: {e}")
        print(f"\u274C Error inserting usernames. Check logs for details.", e)

# ----------------------------------- #
# Main function
# ----------------------------------- #
def main():

    configure_logging()

    reddit = initialize_reddit_client()
    #print("P1")
    
    ensure_table()
    ensure_reddit_database()
    #print("P2")

    with connect_to_database() as connection:

        existing_usernames, current_id = load_existing_usernames(connection)
        #print("P3")
    
        random_usernames = fetch_random_usernames(reddit, existing_usernames)
        #print("P4")
        
        insert_usernames(connection, random_usernames, existing_usernames, current_id)
        #print("P5")
        
    connection.close()
    print("\u2705 Database connection closed.")


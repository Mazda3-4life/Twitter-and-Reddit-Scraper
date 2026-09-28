import os
import logging
import praw
import time
import pymssql
import csv
from dotenv import load_dotenv


# ----------------------------------- #
# Load environment variables
# ----------------------------------- #
load_dotenv()

# ----------------------------------- #
# Database configuration
# ----------------------------------- #
PROXY_FILE = os.getenv("PROXY_FILE")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")


# Connect to the SQL Server database
def get_connection():
    try:
        connection = pymssql.connect(
            server = DB_HOST,
            #user = DB_USER,
            #password = DB_PASSWORD,
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
LOG_DIR = "logs"
try:
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
except Exception as e:
    print(f"\u274C Error creating log directory: {e}")
    exit()
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "errors.log"),
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ----------------------------------- #
# Load username from the database
# ----------------------------------- #
def load_username(connection, username):
    query = """
        SELECT user_id_num 
        FROM usernames 
        WHERE username = %s 
          AND profile_complete = 1 
          AND posts_fetched = 1 
          AND comments_fetched = 1 
          AND user_processed = 0
    """
    try:
        with connection.cursor(as_dict=True) as cursor:
            cursor.execute(query, (username,))
            row = cursor.fetchone()
            if row:
                print(f"\u2705 Found user {username} ready for processing.")
                return row["user_id_num"]
            else:
                print(f"User {username} is either already processed or missing required data.")
                return None
    except Exception as e:
        logging.error(f"Error loading user_id for {username}: {e}")
        print(f"\u274C Error loading user_id for {username}")
        return None


# ----------------------------------- #
# Calculate stats
# ----------------------------------- #
def aggregate_user_statistics(user_id_num, connection):
    tweet_count = 0
    comment_count = 0
    posts_and_comments_mean = 0.0
    avg_num_comments = 0.0
    total_duplicates = 0

    try:
        with connection.cursor() as cursor:
            # Tweet count
            try:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM tweets
                    WHERE user_id_num = %s
                """, (user_id_num,))
                tweet_count = cursor.fetchone()[0]
            except Exception as e:
                logging.error(f"Error counting tweets for user_id_num {user_id_num}: {e}")

            # Comment count
            try:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM comments
                    WHERE user_id_num = %s
                """, (user_id_num,))
                comment_count = cursor.fetchone()[0]

                posts_and_comments_mean = (tweet_count + comment_count) / 2.0
            except Exception as e:
                logging.error(f"Error counting comments for user_id_num {user_id_num}: {e}")

            # Avg number of comments per tweet
            try:
                if tweet_count > 0:
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM comments
                        WHERE user_id_num = %s
                    """, (user_id_num,))
                    total_comments = cursor.fetchone()[0]
                    avg_num_comments = total_comments / tweet_count
            except Exception as e:
                logging.error(f"Error calculating avg comments per tweet for user_id_num {user_id_num}: {e}")

            # Total duplicates (tweets + comments)
            try:
                cursor.execute("""
                    SELECT 
                        COALESCE(c.user_id_num, t.user_id_num) AS user_id_num,
                        COALESCE(duplicate_comments, 0) + COALESCE(duplicate_tweets, 0) AS total_duplicates
                    FROM (
                        SELECT user_id_num, COUNT(*) - COUNT(DISTINCT comment_text) AS duplicate_comments
                        FROM comments
                        GROUP BY user_id_num
                    ) c
                    FULL OUTER JOIN (
                        SELECT user_id_num, COUNT(*) - COUNT(DISTINCT tweet_text) AS duplicate_tweets
                        FROM tweets
                        GROUP BY user_id_num
                    ) t ON c.user_id_num = t.user_id_num
                    WHERE COALESCE(c.user_id_num, t.user_id_num) = %s
                """, (user_id_num,))
                duplicate_row = cursor.fetchone()
                total_duplicates = duplicate_row[1] if duplicate_row and duplicate_row[1] is not None else 0
            except Exception as e:
                logging.error(f"Error counting duplicates for user_id_num {user_id_num}: {e}")

        return tweet_count, comment_count, posts_and_comments_mean, avg_num_comments, total_duplicates

    except Exception as e:
        logging.error(f"Error in aggregate_user_statistics for user_id_num {user_id_num}: {e}")
        return 0, 0, 0.0, 0.0, 0

# ----------------------------------- #
# Cleanup duplicates
# ----------------------------------- #
def cleanup_duplicates(user_id_num, conn):
    try:
        with conn.cursor() as cur:
            # Tweets
            cur.execute("""
                WITH DuplicateTweets AS (
                    SELECT id
                    FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY user_id_num, tweet_text
                            ORDER BY id DESC
                        ) AS rn
                        FROM tweets WHERE user_id_num=%s
                    ) t WHERE rn > 1
                )
                DELETE FROM tweets WHERE id IN (SELECT id FROM DuplicateTweets)
            """, (user_id_num,))
            conn.commit()

            # Comments
            cur.execute("""
                WITH DuplicateComments AS (
                    SELECT id
                    FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY user_id_num, comment_text
                            ORDER BY id DESC
                        ) AS rn
                        FROM comments WHERE user_id_num=%s
                    ) c WHERE rn > 1
                )
                DELETE FROM comments WHERE id IN (SELECT id FROM DuplicateComments)
            """, (user_id_num,))
            conn.commit()
    except Exception as e:
        logging.error(f"Error cleaning duplicates: {e}")
        conn.rollback()

# ----------------------------------- #
# Update Users status
# ----------------------------------- #
def update_user_profile(user_id_num, tweet_count, comment_count, posts_and_comments_mean, avg_num_comments, total_duplicates, conn):
    try:
        with conn.cursor() as cur:
            required_columns = {
                "posts_and_comments_mean": "FLOAT",
                "avg_num_comments": "FLOAT",
                "total_duplicates": "INT"
            }

            for col, col_type in required_columns.items():
                cur.execute("""
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'users' AND COLUMN_NAME = %s
                """, (col,))
                exists = cur.fetchone()[0]

                if exists == 0:
                    cur.execute(f"ALTER TABLE users ADD {col} {col_type}")
                    print(f"Added missing column: {col}")

            cur.execute("""
                UPDATE users
                SET tweets = %s,
                    comments = %s,
                    posts_and_comments_mean = %s,
                    avg_num_comments = %s,
                    total_duplicates = %s,
                    posts_status = 'processed',
                    comments_status = 'processed'
                WHERE user_id_num = %s
            """, (tweet_count, comment_count, posts_and_comments_mean, avg_num_comments, total_duplicates, user_id_num))
            conn.commit()
            print(f"\u2705 Updated stats for user_id_num {user_id_num}")
    except Exception as e:
        logging.error(f"Error updating user profile for {user_id_num}: {e}")
        print(f"\u274C Error updating user profile for {user_id_num}", e)


def update_user_status(user_id_num, conn):
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE usernames
                SET user_processed = 1
                WHERE user_id_num = %s
            """, (user_id_num,))
            conn.commit()
            print(f"\u2705 Updated status for user_id_num {user_id_num}")
    except Exception as e:
        logging.error(f"Error updating user status for {user_id_num}: {e}")
        print(f"\u274C Error updating user status for {user_id_num}", e)

#----------------------------------
# Main function
#----------------------------------
def main(username, conn):
    if not conn:
        print("\u274C Failed to connect to DB.")
        return
    
    user_id = load_username(conn, username)
    if not user_id:
        print("No eligible user found to process. Exiting.")
        conn.commit()
        return

    print(f"Processing user: {username} (User ID: {user_id})")

    try:
        # Aggregate stats
        tweet_count, comment_count, posts_and_comments_mean, avg_num_comments, total_duplicates = aggregate_user_statistics(user_id, conn)

        # Update user profile
        update_user_profile(user_id, tweet_count, comment_count, posts_and_comments_mean, avg_num_comments, total_duplicates, conn)

        # Cleanup duplicates
        cleanup_duplicates(user_id, conn)

        # Update status
        update_user_status(user_id, conn)

        print(f"\u2705 Finished processing {username}\n")
    except Exception as e:
        logging.error(f"Error processing {username}: {e}")
        print(f"\u274C Failed processing {username}\n")

    conn.commit()
    print("\u2705 Database connection closed.")


#Execute 
if __name__ == "__main__":
    main()
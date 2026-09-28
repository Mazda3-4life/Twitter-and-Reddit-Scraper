import os
import logging
import praw
import time
import pymssql
import csv

# ----------------------------------- #
# Load environment variables
# ----------------------------------- #
#load_dotenv()

# ----------------------------------- #
# Constants and configurations
# ----------------------------------- #
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
LOG_DIR = "logs"

# ----------------------------------- #
# Database configuration
# ----------------------------------- #
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
# Load usernames from the database
# ----------------------------------- #

def load_username(connection, username):
    query = """SELECT user_id_num, username FROM usernames WHERE username = %s AND
               profile_complete = 1 AND posts_fetched = 1 AND comments_fetched = 1 AND 
               user_subreddit_profile_complete = 1 AND user_trophies_complete = 1 AND user_processed = 0"""
    

    try:
        with connection.cursor(as_dict=True) as cursor:
            cursor.execute(query, (username,))
            row = cursor.fetchall()

        if row:
            print(f"Found user ready for processing: {username}")
            return row
            
        else:
            print(f"User {username} is not ready for processing or already processed.")
            return None
    
    except Exception as e:
        logging.error(f"Error loading usernames from database: {e}")
        print(f"\u274C Error loading usernames from database. Check logs for details.")
        return None

# ----------------------------------- #
# Change Users user_processed column status in usernames table 
# ----------------------------------- #
def update_user_status(user_id_num, connection, user_processed = None):
    query = """
    UPDATE usernames
    SET 
        user_processed = ISNULL(%s, user_processed)

    WHERE user_id_num = %s
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (user_processed, user_id_num))
            connection.commit()
        print("\u2705 User updated succesfully")
    except Exception as e:
        logging.error(f"Error updating user status for user_id_num {user_id_num}: {e}")
        print(f"\u274C Error updating user status for user_id_num {user_id_num}. Check logs for details.")

def aggregate_user_statistics(user_id_num, connection):
    post_count = 0
    comment_count = 0
    posts_and_comments_mean = 0.0
    avg_num_comments = 0.0
    controversial_count = 0
    edited_count = 0
    trophies_count = 0
    over_18 = 0
    subscribers = 0
    total_duplicates = 0
    try:
        with connection.cursor() as cursor:
            
            # Post table
            try:
                cursor.execute("""
                    SELECT COUNT(*), SUM(num_comments) * 1.0 / NULLIF(COUNT(*), 0)
                    FROM posts 
                    WHERE user_id_num = %s
                """, (user_id_num,))
                post_row = cursor.fetchone()
                post_count = post_row[0]
                avg_num_comments = post_row[1] if post_row[1] is not None else 0.0
            except Exception as e:
                logging.error(f"Error counting posts for user_id_num {user_id_num}: {e}")

            # Comment table
            try:
                cursor.execute("""
                    SELECT COUNT(*), 
                    COUNT(CASE WHEN controversiality = 1 THEN 1 END),
                    COUNT(CASE WHEN edited = 1 THEN 1 END)
                    FROM comments 
                    WHERE user_id_num = %s
                """, (user_id_num,))
                comment_row = cursor.fetchone()
                comment_count = comment_row[0]
                controversial_count = comment_row[1]
                edited_count = comment_row[2]

                posts_and_comments_mean = (post_count + comment_count) / 2.0
            except Exception as e:
                logging.error(f"Error counting comments for user_id_num {user_id_num}: {e}")

            # Total duplicates
            try:           
                cursor.execute("""
                    SELECT 
                        COALESCE(c.user_id_num, p.user_id_num) AS user_id_num,
                        COALESCE(duplicate_comments, 0) + COALESCE(duplicate_posts, 0) AS total_duplicates
                    FROM (
                        SELECT user_id_num, COUNT(*) - COUNT(DISTINCT body) AS duplicate_comments
                        FROM comments
                        GROUP BY user_id_num
                    ) c
                    FULL OUTER JOIN (
                        SELECT user_id_num, COUNT(*) - COUNT(DISTINCT title) AS duplicate_posts
                        FROM posts
                        GROUP BY user_id_num
                    ) p ON c.user_id_num = p.user_id_num
                    WHERE COALESCE(c.user_id_num, p.user_id_num) = %s
                """, (user_id_num,))
                duplicate_row = cursor.fetchone()
                total_duplicates = duplicate_row[1]
                print("\u2705 total_duplicates updated in users table")
            except Exception as e:
                logging.error(f"Error counting duplicates for user_id_num {user_id_num}: {e}")
            
            # Trophie tablr
            try:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM user_trophies
                    WHERE user_id_num = %s
                """, (user_id_num,))
                trophy_row = cursor.fetchone()
                trophies_count = trophy_row[0]
            except Exception as e:
                logging.error(f"Error counting trophies for user_id_num {user_id_num}: {e}")
            
            # Subreddit table
            try:
                cursor.execute("""
                    SELECT over_18, subscribers
                    FROM user_subreddit_profile
                    WHERE user_id_num = %s
                """, (user_id_num,))
                subreddit_row = cursor.fetchone()
                over_18 = subreddit_row[0]
                subscribers = subreddit_row[1]
            except Exception as e:
                logging.error(f"Error processing subreddit table for user_id_num {user_id_num}: {e}")

            return post_count, comment_count, posts_and_comments_mean, avg_num_comments, controversial_count, edited_count, trophies_count, over_18, subscribers, total_duplicates
    except Exception as e:
        logging.error(f"Error counting posts/comments for user_id_num {user_id_num}: {e}")
        return 0, 0, 0.0, 0.0, 0, 0, 0, 0, 0, 0

def cleanup_duplicates(user_id_num, connection):
    try:
        with connection.cursor() as cursor:
        
            # Delete duplicate comments
            cursor.execute("""
                WITH DuplicateComments AS (
                    SELECT id
                    FROM (
                        SELECT 
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY user_id_num, body 
                                ORDER BY created_utc DESC
                            ) AS rn
                        FROM comments
                        WHERE user_id_num = %s
                    ) AS T
                    WHERE T.rn > 1
                )
                DELETE FROM comments WHERE id IN (SELECT id FROM DuplicateComments);
            """, (user_id_num,))
            connection.commit()
            print(f"\u2705 Duplicate comments for user:{user_id_num} removed")

            # Delete duplicate posts
            cursor.execute("""
                WITH DuplicatePosts AS (
                    SELECT id
                    FROM (
                        SELECT 
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY user_id_num, title 
                                ORDER BY created_utc DESC
                            ) AS rn
                        FROM posts
                        WHERE user_id_num = %s
                    ) AS T
                    WHERE T.rn > 1
                )
                DELETE FROM posts WHERE id IN (SELECT id FROM DuplicatePosts);
            """, (user_id_num,))
            connection.commit()
            print(f"\u2705 Duplicate posts for user:{user_id_num} removed")

    except Exception as e:
        connection.rollback()
        logging.error(f"Error in cleanup_duplicates for user_id_num {user_id_num}: {e}")
        print(f"\u274C Error occurred for user {user_id_num}: {e}")

def update_user_profile(user_id_num, post_count, comment_count, posts_and_comments_mean, avg_num_comments, controversial_count, edited_count, trophies_count, over_18, subscribers, total_duplicates, connection):
    try:
        with connection.cursor() as cursor:
            query = """
                UPDATE users
                SET post_count = %s,
                    comment_count = %s,
                    posts_and_comments_mean = %s,
                    avg_num_comments = %s,
                    controversial_count = %s,
                    edited_count = %s,
                    trophies_count = %s,
                    over_18 = %s,
                    subscribers = %s, 
                    total_duplicates = %s
                WHERE user_id_num = %s
            """
            cursor.execute(query, (post_count, comment_count, posts_and_comments_mean,avg_num_comments, controversial_count, edited_count, trophies_count, over_18, subscribers, total_duplicates, user_id_num))
            connection.commit()
    except Exception as e:
        logging.error(f"Error updating columns in users table for user_id_num {user_id_num}: {e}")

# ----------------------------------- #
# main function
# ----------------------------------- #
def main(username):
    connection = get_connection()
    if not connection:
        print(f"\u274C connection to Data Base Failed.")
        return
    
    try:
        user_data = load_username(connection, username)
        if not user_data:
            print("No processing needed for this user.")
            return
        
        user_data = user_data[0]                # list to distionory, do not remove
        user_id_num = user_data["user_id_num"]
        
        print(f"Processing user: {username} (ID: {user_id_num})")

        stats = aggregate_user_statistics(user_id_num, connection)
        update_user_profile(user_id_num, *stats, connection)

        update_user_status(user_id_num, connection, user_processed=1)

        cleanup_duplicates(user_id_num, connection)

        print(f"Finished processing user: {username}")

    except Exception as e:
        logging.error(f"Error processing user {username}: {e}")
        print(f"Failed processing user: {username}", e)
    
    finally:
        connection.close()

#Execute main def
if __name__ == "__main__":
    main("has900original")
import os
import logging
import praw
import time
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
# Connect to the SQL Server database
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
# Database's table checking
# ----------------------------------- #
def check_and_create_tables(connection):
    try:
        table_queries = {
            "users": """
                CREATE TABLE users (
                    user_id_num INT,
                    id NVARCHAR(50) UNIQUE,
                    username NVARCHAR(255) NOT NULL,
                    mbti_type VARCHAR(4) DEFAULT NULL,
                    created_utc BIGINT NOT NULL,
                    is_employee BIT,
                    has_verified_email BIT,
                    comment_karma INT,
                    link_karma INT,
                    total_karma INT,
                    post_count INT DEFAULT 0,
                    comment_count INT DEFAULT 0,
                    is_mod BIT,
                    is_gold BIT,
                    awardee_karma INT,
                    awarder_karma INT,
                    accept_chats BIT NULL,
                    accept_pms BIT NULL,
                    verified BIT,
                    icon_img VARCHAR(MAX),
                    has_subscribed BIT NULL,
                    posts_and_comments_mean FLOAT DEFAULT 0,
                    avg_num_comments FLOAT DEFAULT 0,
                    controversial_count INT DEFAULT 0,
                    edited_count INT DEFAULT 0,
                    trophies_count INT DEFAULT 0,
                    over_18 BIT DEFAULT 0,
                    subscribers INT DEFAULT 0,
                    total_duplicates INT DEFAULT 0,
                    FOREIGN KEY (user_id_num) REFERENCES usernames(user_id_num)
                )
            """,
            "posts": """
                CREATE TABLE posts (
                    user_id_num INT,
                    post_number NVARCHAR(50) NOT NULL,
                    id NVARCHAR(50) PRIMARY KEY,
                    created_utc BIGINT NOT NULL,
                    title NVARCHAR(MAX) NOT NULL,
                    selftext NVARCHAR(MAX),
                    subreddit NVARCHAR(255) NOT NULL,
                    score INT,
                    post_url NVARCHAR(MAX),
                    num_comments INT,
                    FOREIGN KEY (user_id_num) REFERENCES usernames(user_id_num)
                )
            """,
            "comments": """
                CREATE TABLE comments (
                    user_id_num INT,
                    comment_number NVARCHAR(50) NOT NULL,
                    id NVARCHAR(50) PRIMARY KEY,
                    created_utc BIGINT NOT NULL,
                    body NVARCHAR(MAX) NOT NULL,
                    subreddit NVARCHAR(255) NOT NULL,
                    score INT,
                    parent_id NVARCHAR(50),
                    edited BIT NULL,
	                controversiality BIT NULL,
                    FOREIGN KEY (user_id_num) REFERENCES usernames(user_id_num)
                )
            """,
            "user_subreddit_profile": """
                CREATE TABLE user_subreddit_profile (
                    user_id_num INT NOT NULL PRIMARY KEY,
                    title NVARCHAR(255),
                    public_description NVARCHAR(255),
                    over_18 BIT,
                    subscribers INT,
                    banner_img NVARCHAR(MAX),
                    icon_img NVARCHAR(MAX),
                    FOREIGN KEY (user_id_num) REFERENCES usernames(user_id_num)
                )         
            """,
            "user_trophies" : """
            CREATE TABLE user_trophies (
                user_id_num INT NOT NULL,
                trophy_id INT IDENTITY(1,1) PRIMARY KEY,
                trophy_name VARCHAR(255),
                descriptions VARCHAR(255),
                granted_at BIGINT,
                icon_url VARCHAR(255),
                FOREIGN KEY (user_id_num) REFERENCES usernames(user_id_num)
            )
            """
        }

        with connection.cursor() as cursor:
            for table_name, create_query in table_queries.items():
                check_query = f"""
                    SELECT TABLE_NAME 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME = '{table_name}'
                """
                cursor.execute(check_query)
                if cursor.fetchone():
                    print(f"\u2705 Table '{table_name}' already exists.")
                else:
                    print(f"\u26A0 Table '{table_name}' does not exist. Creating it...")
                    cursor.execute(create_query)
                    connection.commit()
                    print(f"\u2705 Table '{table_name}' created successfully.")
    except Exception as e:
        print(f"\u274C Error while checking or creating tables: {e}")
        logging.error(f"Error while checking or creating tables: {e}")

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
# Change Users data, Posts, Comments status in usernames table 
# ----------------------------------- #
def update_user_status(user_id_num, connection, profile_complete=None, posts_fetched=None, comments_fetched=None,  user_subreddit_profile_complete=None, user_trophies_complete=None):
    query = """
    UPDATE usernames
    SET 
        profile_complete = ISNULL(%s, profile_complete),
        posts_fetched = ISNULL(%s, posts_fetched),
        comments_fetched = ISNULL(%s, comments_fetched),
        user_subreddit_profile_complete = ISNULL(%s,user_subreddit_profile_complete),
        user_trophies_complete = ISNULL(%s, user_trophies_complete)

    WHERE user_id_num = %s
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (profile_complete, posts_fetched, comments_fetched, user_subreddit_profile_complete, user_trophies_complete, user_id_num))
            connection.commit()

    except Exception as e:
        logging.error(f"Error updating user status for user_id_num {user_id_num}: {e}")
        print(f"\u274C Error updating user status for user_id_num {user_id_num}. Check logs for details.")


# ----------------------------------- #
# Insert data into the users table
# ----------------------------------- #
def insert_user(user_data, connection):
    query = """
    IF EXISTS (SELECT 1 FROM users WHERE id = %s)
    BEGIN
        UPDATE users
        SET username = %s, created_utc = %s, is_employee = %s,
            has_verified_email = %s, comment_karma = %s,
            link_karma = %s, total_karma = %s, is_mod = %s, is_gold = %s,
            awardee_karma = %s, awarder_karma = %s, accept_chats = %s, accept_pms = %s,
            verified = %s, icon_img = %s, has_subscribed = %s
        WHERE id = %s
    END
    ELSE
    BEGIN
        INSERT INTO users (
            user_id_num, id, username, created_utc, is_employee, 
            has_verified_email, comment_karma, link_karma, total_karma,
            is_mod, is_gold, awardee_karma, awarder_karma, accept_chats,
            accept_pms, verified, icon_img, has_subscribed
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    END
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (
                user_data["id"],  # WHERE

                user_data["username"], user_data["created_utc"], user_data["is_employee"], # UPDATE section
                user_data["has_verified_email"], user_data["comment_karma"],
                user_data["link_karma"], user_data["total_karma"],
                user_data["is_mod"], user_data["is_gold"],
                user_data["awardee_karma"], user_data["awarder_karma"],
                user_data["accept_chats"], user_data["accept_pms"],
                user_data["verified"], user_data["icon_img"], user_data["has_subscribed"],
                user_data["id"],  # WHERE again

                user_data["user_id_num"], user_data["id"], user_data["username"], # INSERT section
                user_data["created_utc"], user_data["is_employee"],
                user_data["has_verified_email"], user_data["comment_karma"],
                user_data["link_karma"], user_data["total_karma"],
                user_data["is_mod"], user_data["is_gold"],
                user_data["awardee_karma"], user_data["awarder_karma"],
                user_data["accept_chats"], user_data["accept_pms"],
                user_data["verified"], user_data["icon_img"], user_data["has_subscribed"]
            ))
            connection.commit()
    except Exception as e:
        logging.error(f"Error inserting user {user_data['username']}: {e}")
        print(f"\u274C Error inserting user {user_data['username']}. Check logs for details.")

# ----------------------------------- #
# Insert data into the posts table
# ----------------------------------- #
def insert_post(post_data, connection):
    query = """
    IF EXISTS (SELECT 1 FROM posts WHERE id = %s)
    BEGIN
        UPDATE posts
        SET title = %s, selftext = %s, subreddit = %s, score = %s, post_url = %s, num_comments = %s
        WHERE id = %s
    END
    ELSE
    BEGIN
        INSERT INTO posts (
            user_id_num, post_number, id, created_utc, title, selftext, 
            subreddit, score, post_url, num_comments
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    END
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (
                post_data["id"], # Where
                # update section
                post_data["title"], post_data["selftext"], post_data["subreddit"],
                post_data["score"], post_data["post_url"], post_data["num_comments"],
                
                post_data["id"], # where
                # insert section
                post_data["user_id_num"], post_data["post_number"], post_data["id"], post_data["created_utc"], post_data["title"],
                post_data["selftext"], post_data["subreddit"], post_data["score"], post_data["post_url"], post_data["num_comments"]
            ))
            connection.commit()
    except Exception as e:
        logging.error(f"Error inserting post {post_data['id']}: {e}")
        print(f"\u274C Error inserting post {post_data['id']}. Check logs for details.")

# ----------------------------------- #
# Insert data into the comments table
# ----------------------------------- #
def insert_comment(comment_data, connection):
    query = """
    IF EXISTS (SELECT 1 FROM comments WHERE id = %s)
    BEGIN
        UPDATE comments
        SET body = %s, subreddit = %s, score = %s, parent_id = %s, edited = %s, controversiality = %s
        WHERE id = %s
    END
    ELSE
    BEGIN
        INSERT INTO comments (
            user_id_num, comment_number, id, created_utc, body, subreddit, 
            score, parent_id,edited, controversiality
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    END
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (
                comment_data["id"],
                comment_data["body"], comment_data["subreddit"], comment_data["score"],  
                comment_data["parent_id"], comment_data["edited"], comment_data["controversiality"],
                
                comment_data["id"],

                comment_data["user_id_num"], comment_data["comment_number"], comment_data["id"], comment_data["created_utc"], comment_data["body"], 
                comment_data["subreddit"], comment_data["score"], comment_data["parent_id"], 
                comment_data["edited"], comment_data["controversiality"] 
            ))
            connection.commit()
    except Exception as e:
        logging.error(f"Error inserting comment {comment_data['id']}: {e}")
        print(f"\u274C Error inserting comment {comment_data['id']}. Check logs for details.")

# ----------------------------------- #
# Insert data into user_subreddit_profile table
# ----------------------------------- #
def insert_subreddit_profile(subreddit_data, connection):
    query = """
    IF EXISTS (SELECT 1 FROM user_subreddit_profile WHERE user_id_num = %s)
    BEGIN
        UPDATE user_subreddit_profile
        SET title = %s, public_description = %s, over_18 = %s, subscribers = %s,
        banner_img = %s, icon_img = %s
        WHERE user_id_num = %s
    END
    ELSE
    BEGIN 
        INSERT INTO user_subreddit_profile(
            user_id_num, title, public_description, over_18, subscribers, banner_img, 
            icon_img
        )VALUES (%s, %s, %s, %s, %s, %s, %s)
    END
    """
    try: 
        with connection.cursor() as cursor:
            cursor.execute(query, (
                subreddit_data["user_id_num"],
                subreddit_data["title"], subreddit_data["public_description"], 
                subreddit_data["over_18"], subreddit_data["subscribers"],
                subreddit_data["banner_img"], subreddit_data["icon_img"],
                
                subreddit_data["user_id_num"],

                subreddit_data["user_id_num"],
                subreddit_data["title"], subreddit_data["public_description"], 
                subreddit_data["over_18"], subreddit_data["subscribers"],
                subreddit_data["banner_img"], subreddit_data["icon_img"]
            ))
            connection.commit()
    except Exception as e:
        logging.error(f"Error inserting subreddit_profile {subreddit_data['user_id_num']}: {e}")
        print(f"\u274C Error inserting subreddit_profile {subreddit_data['user_id_num']}. Check logs for details.")

# ----------------------------------- #
# Insert data into table
# ----------------------------------- #
def insert_user_trophies(trophies_data, connection):
    query = """
    IF EXISTS (SELECT 1 FROM user_trophies WHERE user_id_num = %s AND trophy_name = %s)
    BEGIN
        UPDATE user_trophies
        SET descriptions = %s, granted_at = %s, icon_url = %s
        WHERE user_id_num = %s AND trophy_name = %s
    END
    ELSE 
    BEGIN
        INSERT INTO user_trophies(
            user_id_num, trophy_name, descriptions, granted_at, icon_url
        ) VALUES(%s, %s, %s, %s, %s)
    END    
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (
                trophies_data["user_id_num"], trophies_data["trophy_name"],
                trophies_data["descriptions"], trophies_data["granted_at"], trophies_data["icon_url"],

                trophies_data["user_id_num"], trophies_data["trophy_name"],

                trophies_data["user_id_num"], trophies_data["trophy_name"],
                trophies_data["descriptions"], trophies_data["granted_at"], trophies_data["icon_url"]
            ))
            connection.commit()
    except Exception as e:
        logging.error(f"Error inserting subreddit_profile {trophies_data["user_id_num"]}: {e}")
        print(f"\u274C Error inserting subreddit_profile {trophies_data["user_id_num"]}. Check logs for details.")

# ----------------------------------- #
# Safe function (for test)
# ----------------------------------- #
def safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

# ----------------------------------- #
# Load username from the database
# ----------------------------------- #
def load_username(connection, username):
    query = """SELECT user_id_num, username, profile_complete, posts_fetched, comments_fetched,
               user_subreddit_profile_complete, user_trophies_complete
               FROM usernames
               WHERE username = %s"""
               
    try:
        with connection.cursor(as_dict=True) as cursor:
            cursor.execute(query, (username,))
            row = cursor.fetchone()

        print(f"\u2705 Loaded {username} from database.")
        
    except Exception as e:
        logging.error(f"Error loading username from database: {e}")
        print(f"\u274C Error loading username from database. Check logs for details. ", e)
        exit()
    return row

# ----------------------------------- #
# Main function of project
# ----------------------------------- #
def main(username):
    connection = get_connection()
    
    if not connection:
        return
    try:    
        reddit = initialize_reddit_client()
        
        check_and_create_tables(connection)
        user_info = load_username(connection, username)

        if not user_info:
            print("User not found in DB. Exiting.")
            return
        
        user_id_num = user_info["user_id_num"]
        
        need_profile = not user_info["profile_complete"]
        need_posts = not user_info["posts_fetched"]
        need_comments = not user_info["comments_fetched"]
        need_subreddit = not user_info["user_subreddit_profile_complete"]
        need_trophies = not user_info["user_trophies_complete"]
        
        print(f"Processing {username} (ID: {user_id_num})")
        
        
        user = reddit.redditor(username)

        if need_profile:
            # Fetch user's profile data
            try:
                user_data = {
                    "user_id_num": user_id_num,
                    "id": user.id,
                    "username": username,
                    "created_utc": int(user.created_utc),
                    "is_employee": user.is_employee,
                    "has_verified_email": user.has_verified_email,
                    "comment_karma": user.comment_karma,
                    "link_karma": user.link_karma,
                    "total_karma": user.total_karma,
                    "is_mod": user.is_mod,
                    "is_gold": user.is_gold,
                    "awardee_karma": user.awardee_karma,
                    "awarder_karma": user.awarder_karma,
                    "accept_chats": getattr(user, "accept_chats", None),
                    "accept_pms": getattr(user, "accept_pms", None),
                    "verified": user.verified,
                    "icon_img": getattr(user, "icon_img", None) if isinstance(getattr(user, "icon_img", None), str) else None,
                    "has_subscribed": getattr(getattr(user, "subreddit", None), "user_is_subscriber", None)
                }
                insert_user(user_data, connection)
                print(f"\u2705 Inserted user's data in database for user: {username}")
                update_user_status(user_id_num, connection, profile_complete=1)
            except Exception as e:
                post_success = False
                logging.error(f"Error inserting user {user.id}: {e}")
        
        if need_posts:        
            # Fetch user's posts
            post_success = True
            for post in user.submissions.new(limit=100):
                try:
                    post_data = {
                        "user_id_num": user_id_num,
                        "post_number": post.id,
                        "id": post.id,
                        "created_utc": int(post.created_utc),
                        "title": post.title,
                        "selftext": post.selftext,
                        "subreddit": post.subreddit.display_name,
                        "score": post.score,
                        "post_url": post.url,
                        "num_comments": post.num_comments                        
                    }
                    insert_post(post_data, connection)
                except Exception as e:
                    post_success = False
                    logging.error(f"Error inserting post {post.id}: {e}")
            if post_success:
                print(f"\u2705 Inserted posts in database for user: {username}")
                update_user_status(user_id_num, connection, posts_fetched=1)

        if need_comments:
            # Fetch user's comments
            comment_success = True
            for comment in user.comments.new(limit=100):
                try:
                    comment_data = {
                        "user_id_num": user_id_num,
                        "comment_number": comment.id,
                        "id": comment.id,
                        "created_utc": int(comment.created_utc),
                        "body": comment.body,
                        "subreddit": comment.subreddit.display_name,
                        "score": comment.score,
                        "parent_id": comment.parent_id.split('_')[-1],
                        "edited": bool(getattr(comment, "edited", False)),
                        "controversiality":getattr(comment, "controversiality", None)
                    }
                    insert_comment(comment_data, connection)
                except Exception as e:
                    comment_success = False
                    logging.error(f"Error inserting comment {comment.id}: {e}")
            if comment_success:
                print(f"\u2705 Inserted comments in database for user: {username}")
                update_user_status(user_id_num, connection, comments_fetched=1)

        if need_subreddit:    
            # Fetch user's subreddit profile data
            try:
                subreddit = user.subreddit
                subreddit_data = {
                    "user_id_num": user_id_num,
                    "title": subreddit.title,
                    "public_description": subreddit.public_description,
                    "over_18": subreddit.over18,
                    "subscribers": subreddit.subscribers,
                    "banner_img": subreddit.banner_img,
                    "icon_img": subreddit.icon_img
                }
                insert_subreddit_profile(subreddit_data, connection)
                print(f"\u2705 Inserted subreddits in database for user: {username}")
                update_user_status(user_id_num, connection, user_subreddit_profile_complete=1)
            except Exception as e:
                logging.error(f"Error inserting subreddit profile for {username}: {e}")   

        if need_trophies:    
            # Fetch user's trophies
            try:
                trophies = user.trophies()
                for trophy in trophies:
                    trophy_data = {
                        "user_id_num": user_id_num,
                        "trophy_name": trophy.name,
                        "descriptions": trophy.description,
                        "granted_at": safe_int(getattr(trophy, "granted_at", None)),
                        "icon_url": getattr(trophy, "icon_url", "")
                    }
                    insert_user_trophies(trophy_data, connection)
                print(f"\u2705 Inserted trophies in database for user: {username}")
                update_user_status(user_id_num, connection, user_trophies_complete=1)
            except Exception as e:
                logging.error(f"Error inserting trophy {username}: {e}")
                print(f"\u274C Error processing user {username}. Check logs for details.")
        
        print(f"\n\u2705 Completed processing.")
    finally:
        connection.close()

# ----------------------------------- #
# Call the main function
# ----------------------------------- #

if __name__ == "__main__":
    #username = input("Enter your username:").strip()
    main("has900original")

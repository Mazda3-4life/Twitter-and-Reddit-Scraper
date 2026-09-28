# Twitter and Reddit Scraper

A Python-based data collection system for **Twitter/X and Reddit** that collects user profiles, posts, replies/comments, and additional account information and stores the results in a **Microsoft SQL Server** database.

The project provides two main workflows:

- **Collectors** — discover and process multiple users.
- **Specific-user collectors** — collect and process data for a particular username.

The Twitter/X components use HTML scraping through a configurable web endpoint such as Nitter, while Reddit components use the **Reddit API through PRAW**.

---

## Features

### Twitter/X

- Collect usernames associated with hashtags.
- Collect Twitter/X user profiles.
- Collect tweets.
- Collect retweets with comments.
- Collect replies made by a user.
- Support for proxy-based scraping.
- Non-proxy scraping alternatives.
- Process multiple users stored in SQL Server.
- Process a specific Twitter/X username.
- Track processing status in the database.
- Retry failed requests.
- Logging of errors to `logs/errors.log`.

### Reddit

- Discover Reddit usernames from `/r/all`.
- Process a specific Reddit username.
- Collect Reddit user profile information.
- Collect posts submitted by users.
- Collect comments made by users.
- Collect subreddit-profile information.
- Collect Reddit trophies.
- Calculate aggregated user statistics.
- Detect and clean duplicate records.
- Store all collected information in SQL Server.
- Track which stages of processing have been completed.

---

## Project Structure

```text
Twitter-and-Reddit-Scraper/
│
├── reddit_collectors/
│   ├── reddit_data_collector.py
│   └── reddit_username_collector.py
│
├── reddit_specific_user/
│   ├── reddit_specific_user_processor.py
│   ├── reddit_specific_username_collector.py
│
├── twitter_collectors/
│   ├── twitter_scraper_withoutproxy_profiles.py
│   ├── twitter_scraper_withoutproxy_replies.py
│   ├── twitter_scraper_withoutproxy_tweets.py
│   ├── twitter_scraper_withproxy_profiles.py
│   ├── twitter_scraper_withproxy_replies.py
│   ├── twitter_scraper_withproxy_tweets.py
│   ├── twitter_username_collector.py
│   └── twitter_username_withoutproxy_collector.py
│
└── twitter_specific_user/
    ├── twitter_specific_user_data_processor.py
    ├── twitter_specific_user_profile_collector.py
    ├── twitter_specific_user_replies_collector.py
    ├── twitter_specific_user_tweets_collector.py
    └── twitter_specific_username_collector.py
```

---

# Architecture

The project follows a database-driven processing pipeline.

```text
                    ┌─────────────────────┐
                    │   Username Source   │
                    └──────────┬──────────┘
                               │
             ┌─────────────────┴─────────────────┐
             │                                   │
             ▼                                   ▼
      Twitter/X Collectors                Reddit Collectors
             │                                   │
             └─────────────────┬─────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   SQL Server DB     │
                    │                     │
                    │ usernames           │
                    │ users                │
                    │ posts                │
                    │ comments             │
                    │ tweets               │
                    │ ...                 │
                    └──────────┬──────────┘
                               │
                               ▼
                    Specific User Processing
                               │
                               ▼
                       Aggregated Statistics
```

The `usernames` table acts as the central queue. Boolean status columns indicate which stages of the collection pipeline have already been completed.

---

# Requirements

- Python 3.8+
- Microsoft SQL Server
- SQL Server database access
- Internet access
- Reddit API credentials for Reddit collection
- A compatible Twitter/X scraping endpoint for the Twitter collectors
- Proxies for the proxy-enabled Twitter collectors

## Python Dependencies

The project uses the following packages:

```bash
pip install requests
pip install pandas
pip install pymssql
pip install beautifulsoup4
pip install python-dotenv
pip install praw
pip install numpy
```

# Configuration

Create a `.env` file in the project root or modify `example.env`.

A typical configuration contains:

```env
DB_HOST=localhost
DB_NAME=social_media_database

DB_USER=your_sql_username
DB_PASSWORD=your_sql_password

DOMAIN=https://your-twitter-scraping-endpoint/

PROXY_FILE=proxies.csv

MAX_PAGES_PER_PERSON=50

CLIENT_ID=your_reddit_client_id
CLIENT_SECRET=your_reddit_client_secret
USER_AGENT=your_reddit_user_agent
```

Not every variable is required by every script.

---

## Environment Variables

| Variable               | Used for                                      |
| ---------------------- | --------------------------------------------- |
| `DB_HOST`              | SQL Server hostname/address                   |
| `DB_NAME`              | SQL Server database name                      |
| `DB_USER`              | Database username where applicable            |
| `DB_PASSWORD`          | Database password where applicable            |
| `DOMAIN`               | Twitter/X scraping endpoint                   |
| `PROXY_FILE`           | CSV file containing proxies                   |
| `MAX_PAGES_PER_PERSON` | Maximum pages used by some Twitter collectors |
| `CLIENT_ID`            | Reddit API client ID                          |
| `CLIENT_SECRET`        | Reddit API client secret                      |
| `USER_AGENT`           | Reddit API user agent                         |

**Do not commit your `.env` file or API credentials to GitHub.**

---

# Reddit

Reddit collection uses [PRAW](https://praw.readthedocs.io/) to communicate with Reddit's API.

## Reddit API Setup

Create a Reddit application and obtain:

```env
CLIENT_ID=...
CLIENT_SECRET=...
USER_AGENT=...
```

The project initializes PRAW approximately as follows:

```python
reddit = praw.Reddit(
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    user_agent=os.getenv("USER_AGENT")
)
```

---

# Reddit Collectors

## 1. Collect Reddit Usernames

`reddit_collectors/reddit_username_collector.py`

This collector searches posts from `/r/all` and extracts usernames from submitted content.
The discovered usernames are stored in the `usernames` SQL Server table.

Run:

```bash
python reddit_collectors/reddit_username_collector.py
```

## 2. Collect Reddit User Data

`reddit_collectors/reddit_data_collector.py`

This script processes usernames stored in the database and collects:

### User information

- Reddit user ID
- Username
- Account creation time
- Comment karma
- Link karma
- Total karma
- Moderator status
- Gold status
- Verification information
- Chat/PM settings
- Avatar information

### Posts

For each user, the collector stores information such as:

- Post ID
- Creation time
- Title
- Body/selftext
- Subreddit
- Score
- URL
- Number of comments

### Comments

The collector stores:

- Comment ID
- Creation time
- Comment body
- Subreddit
- Score
- Parent ID
- Edited status
- Controversiality

### Additional Reddit information

The collector can also collect:

- User's subreddit profile
- Subreddit description
- Subscriber count
- NSFW status
- Banner image
- Icon image
- Reddit trophies

Run:

```bash
python reddit_collectors/reddit_data_collector.py
```

---

# Reddit Specific User

The `reddit_specific_user/` directory is intended for processing a single Reddit account.

## Add a Specific Username

```bash
python reddit_specific_user/reddit_specific_username_collector.py
```

The username is checked through Reddit and added to the database if it does not already exist.

---

## Collect Data for a Specific User

```bash
python reddit_specific_user/reddit_specific_username_data_collector.py
```

This collects the available profile, post, comment, subreddit-profile, and trophy information for the selected user.

The current script contains a username directly in its `main()` call, so change that value before running it if necessary.

---

# Twitter/X

The Twitter/X portion uses HTML parsing with **BeautifulSoup**.

The scraper expects `DOMAIN` to point to a compatible Twitter/X HTML endpoint. Several scripts are designed around Nitter-style page structures such as:

```text
timeline-item
tweet-content
tweet-header
fullname-and-username
show-more
```

Because these HTML structures depend on the scraping endpoint, changes to the target service may require modifications to the parsers.

---

# Twitter/X Username Collection

## With Proxies

```bash
python twitter_collectors/twitter_username_collector.py
```

This collector searches configured hashtags and extracts usernames from the returned pages.

Hashtags are configured inside the script:

```python
HASHTAGS = ["spacex"]
```

Change this list to the hashtags you want to collect.

For example:

```python
HASHTAGS = [
    "spacex",
    "nasa",
    "python"
]
```

---

## Without Proxies

```bash
python twitter_collectors/twitter_username_withoutproxy_collector.py
```

This version performs the same general task without the proxy rotation mechanism.

---

# Proxy Configuration

The proxy-enabled Twitter collectors read proxies from a CSV file.

The expected column name is:

```text
Proxy Link
```

Example:

```csv
Proxy Link
http://127.0.0.1:8080
http://127.0.0.1:8081
http://127.0.0.1:8082
```

Set the file in `.env`:

```env
PROXY_FILE=proxies.csv
```

The proxy-enabled collectors randomly select proxies and implement retry/failure handling.

---

# Twitter/X Data Collection

The project provides separate collectors for profiles, tweets, and replies.

## Without Proxies

### Profiles

```bash
python twitter_collectors/twitter_scraper_withoutproxy_profiles.py
```

### Tweets

```bash
python twitter_collectors/twitter_scraper_withoutproxy_tweets.py
```

### Replies

```bash
python twitter_collectors/twitter_scraper_withoutproxy_replies.py
```

---

## With Proxies

### Profiles

```bash
python twitter_collectors/twitter_scraper_withproxy_profiles.py
```

### Tweets

```bash
python twitter_collectors/twitter_scraper_withproxy_tweets.py
```

### Replies

```bash
python twitter_collectors/twitter_scraper_withproxy_replies.py
```

The tweet collectors distinguish between:

- Original tweets
- Retweets with comments

The default tweet collection target in the scraper is:

```python
TARGET_COUNT = 100
```

---

# Twitter/X Specific User

The `twitter_specific_user/` directory provides a workflow for collecting information about one particular username.

## Add a Specific Username

```bash
python twitter_specific_user/twitter_specific_username_collector.py
```

The script asks for:

```text
username:
```

It verifies the username through the configured scraping endpoint and adds it to the database.

---

## Collect Profile

```bash
python twitter_specific_user/twitter_specific_user_profile_collector.py
```

This collects account/profile information and stores it in the database.

---

## Collect Tweets

```bash
python twitter_specific_user/twitter_specific_user_tweets_collector.py
```

The collector retrieves tweets and retweets with comments from the specified user.

---

## Collect Replies

```bash
python twitter_specific_user/twitter_specific_user_replies_collector.py
```

This collects replies made by the selected user.

---

## Process Twitter/X User

```bash
python twitter_specific_user/twitter_specific_user_data_processor.py
```

The processor aggregates information from the collected data and updates the user's processing status.

---

# Database

The project uses **Microsoft SQL Server** through `pymssql`.

Depending on the workflow, the scripts create and use tables including:

```text
usernames
users
tweets
comments
posts
user_subreddit_profile
user_trophies
```

## `usernames`

The central table contains information such as:

```text
user_id_num
username
hashtag
profile_complete
posts_fetched
comments_fetched
user_subreddit_profile_complete
user_trophies_complete
user_processed
user_personality
```

The status columns allow the collectors to determine which processing stages still need to be performed.

---

# Processing Workflow

A typical Reddit workflow is:

```text
1. Discover usernames
        │
        ▼
2. Store usernames
        │
        ▼
3. Collect profile information
        │
        ▼
4. Collect posts
        │
        ▼
5. Collect comments
        │
        ▼
6. Collect subreddit profile
        │
        ▼
7. Collect trophies
        │
        ▼
8. Aggregate statistics
        │
        ▼
9. Clean duplicate records
```

A typical Twitter/X workflow is:

```text
1. Search hashtag
        │
        ▼
2. Extract usernames
        │
        ▼
3. Store usernames
        │
        ▼
4. Collect profile
        │
        ├───────────────┐
        ▼               ▼
     Tweets           Replies
        │               │
        └───────┬───────┘
                ▼
        Process user data
```

---

# Logging

The collectors create a `logs` directory when necessary.

Errors are written to:

```text
logs/errors.log
```

Logging uses Python's built-in `logging` module.

This is particularly useful for long-running scraping jobs where individual requests may fail while the rest of the collection process continues.

---

# Important Notes

## Twitter/X scraping endpoint

The Twitter/X collectors depend on the HTML structure of the configured `DOMAIN`.

If the target service changes its HTML structure, selectors such as:

```text
timeline-item
tweet-content
tweet-header
fullname-and-username
```

may need to be updated.

## Reddit API limits

Reddit collection is performed through PRAW and is therefore subject to Reddit API policies and rate limits.

## Database permissions

The SQL Server account must have sufficient permissions to:

- Create databases/tables where required
- Insert records
- Update records
- Delete duplicate records
- Query existing records

# Disclaimer

This project is intended for research, data collection, and educational purposes.

# License

MIT Licence

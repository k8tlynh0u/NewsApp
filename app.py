# ==============================================================================
#      NEWS MENTION, SUMMARY & SENTIMENT ANALYZER - WEB APPLICATION (V4 - Corrected & DEPLOYMENT-READY)
#
# This Streamlit application merges the command-line script's logic with a
# web interface, including article title extraction.
# Secrets are handled by Streamlit's secrets management for secure deployment.
# ==============================================================================

# --- STEP 1: IMPORT ALL TOOLS ---
import streamlit as st
import os
import smtplib
from datetime import datetime, timedelta
from urllib.parse import quote
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import feedparser
import spacy
from newsapi.newsapi_client import NewsApiClient
from newspaper import Article, Config
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


# --- STEP 2: SETUP & CONFIGURATION (Wrapped in caching functions) ---

# @st.cache_resource ensures these heavy objects are loaded only once.
@st.cache_resource
def setup_openai_client():
    """Sets up and returns the OpenAI client, using Streamlit secrets."""
    try:
        # MODIFIED: Get API key from st.secrets
        openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        if not openai_client.api_key:
            st.error("OpenAI API key not found in Streamlit secrets.")
            st.stop()
        return openai_client
    except Exception as e:
        st.error(f"Could not set up OpenAI client: {e}")
        st.stop()

@st.cache_resource
def setup_spacy_model():
    """Loads and returns the spaCy NLP model."""
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        st.warning("spaCy model not found. Downloading 'en_core_web_sm'...")
        from spacy.cli import download
        download("en_core_web_sm")
        return spacy.load("en_core_web_sm")

@st.cache_resource
def get_webdriver_path():
    """Installs and returns the path to the Chrome WebDriver."""
    try:
        # Note: This is for local running. On Streamlit Cloud, the path is handled automatically.
        return ChromeDriverManager().install()
    except Exception as e:
        st.error(f"Could not set up Selenium WebDriver. Please ensure Google Chrome is installed. Error: {e}")
        st.stop()

# --- Load all necessary models and clients ---
openai_client = setup_openai_client()
nlp = setup_spacy_model()
chrome_driver_path = get_webdriver_path()

# --- API & Email Configuration (MODIFIED TO USE STREAMLIT SECRETS) ---
MY_API_KEY = st.secrets["NEWSAPI_KEY"]
SENDER_EMAIL = st.secrets["SENDER_EMAIL"]
SENDER_PASSWORD = st.secrets["SENDER_PASSWORD"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# --- STEP 3: HELPER FUNCTIONS (Integrated with title extraction) ---

def fetch_from_google_rss(person_name, from_date, to_date):
    urls_found = []
    try:
        query_terms = f'"{person_name}" after:{from_date.strftime("%Y-%m-%d")} before:{to_date.strftime("%Y-%m-%d")}'
        rss_url = f"https://news.google.com/rss/search?q={quote(query_terms)}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            urls_found.append(entry.get("link", ""))
        return urls_found
    except Exception:
        return []

def fetch_from_newsapi(api_client, person_name, from_date, to_date):
    urls_found = []
    try:
        all_articles = api_client.get_everything(
            q=f'"{person_name}"', from_param=from_date.isoformat(), to=to_date.isoformat(),
            language='en', sort_by='relevancy'
        )
        for article in all_articles.get('articles', []):
            urls_found.append(article['url'])
        return urls_found
    except Exception:
        return []

def convert_google_news_link(google_news_url: str) -> str | None:
    if 'google.com' not in google_news_url:
        return google_news_url
    
    # These options are crucial for running Selenium on Streamlit Cloud
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    
    driver = None
    try:
        # On Streamlit Cloud, we don't need webdriver-manager.
        # It finds the chromedriver automatically if you've listed it in packages.txt
        service = ChromeService()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(google_news_url)
        WebDriverWait(driver, 15).until(lambda d: "google.com" not in d.current_url)
        return driver.current_url
    except Exception:
        return google_news_url # Fallback to original URL on error
    finally:
        if driver: driver.quit()

def process_article(url, name_to_find):
    """
    Downloads an article, extracts its title, full text, and finds sentences with the name.
    Returns a tuple: (title, found_sentences, article_full_text).
    Returns (None, None, None) if the article could not be read.
    """
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        
        article = Article(url, config=config)
        article.download()
        article.parse()

        title = article.title if article.title else "Title Not Found"
        
        if not article.text:
            return (title, [], None)
        
        full_text = article.text
        doc = nlp(full_text)
        found_sentences = [s.text.strip().replace('\n', ' ') for s in doc.sents if name_to_find.lower() in s.text.lower()]
        return (title, found_sentences, full_text)
    except Exception:
        return (None, None, None)

def get_summary_from_gpt(article_text):
    if not article_text: return "Article text was empty; summary could not be generated."
    system_prompt = "You are an expert news editor. Create a concise, neutral, two-sentence summary of the provided news article text."
    user_prompt = f"Please summarize the following article text:\n\n---\n\n{article_text}"
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.2, max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e: return f"Summary generation failed: {e}"

def get_sentiment_from_gpt(person_name, sentences):
    if not sentences: return "No mentions found; sentiment not analyzed."
    context_text = " ".join(sentences)
    system_prompt = "You are an expert news analyst. Determine if the sentiment of a news mention towards a person is Positive, Negative, or Neutral. Base your judgment ONLY on the provided text."
    user_prompt = f"Person: {person_name}\nSentences: \"{context_text}\"\n\nFormat your response as: Sentiment: [Positive/Negative/Neutral]. Justification: [A brief, one-sentence explanation.]"
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0, max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e: return f"Sentiment analysis failed: {e}"

def send_email_with_attachment(subject, body, recipient_email, file_path):
    if not SENDER_PASSWORD:
        st.error("Email password not found in Streamlit secrets. Cannot send email.")
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        with open(file_path, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename= {os.path.basename(file_path)}')
        msg.attach(part)
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"An error occurred while sending the email: {e}")
        return False

# --- STEP 4: STREAMLIT WEB APPLICATION INTERFACE ---

st.set_page_config(page_title="News & Sentiment Analyzer", layout="wide", page_icon="🤖")

st.title("🤖 News Mention, Summary & Sentiment Analyzer")
st.markdown("This tool scours the web for news about a specific person on a given day, then uses AI to summarize each article and analyze the sentiment of the mentions.")

col1, col2 = st.columns(2)
with col1:
    person_name = st.text_input("👤 **Person's Full Name**", placeholder="e.g., Taylor Swift")
    date_input = st.date_input("🗓️ **Date to Search**")
with col2:
    recipient_email = st.text_input("✉️ **Your Email Address (Optional)**", placeholder="Enter your email to receive the report")

if st.button("🚀 Generate Report", type="primary", use_container_width=True):
    if not person_name:
        st.warning("Please enter a person's name to start the analysis.")
        st.stop()

    from_date = date_input
    to_date = from_date + timedelta(days=1)
    
    with st.spinner(f"🔍 Searching Google News and NewsAPI for '{person_name}'..."):
        # The API key for newsapi_client is already set from st.secrets
        newsapi_client = NewsApiClient(api_key=MY_API_KEY)
        google_urls = fetch_from_google_rss(person_name, from_date, to_date)
        newsapi_urls = fetch_from_newsapi(newsapi_client, person_name, from_date, to_date)
        unique_raw_urls = sorted(list(set(google_urls + newsapi_urls)))
    
    if not unique_raw_urls:
        st.error(f"No articles found for '{person_name}' on {from_date.strftime('%Y-%m-%d')}. Please try another name or date.")
        st.stop()

    st.success(f"Found {len(unique_raw_urls)} potential articles. Now cleaning and analyzing...")
    
    with st.spinner("Resolving links and preparing for analysis... This may take a moment."):
        # Use a list comprehension for a cleaner look
        final_urls_set = {convert_google_news_link(url) for url in unique_raw_urls}
        final_urls_list = sorted([url for url in final_urls_set if url])
    
    results = {}
    unreadable_articles = []
    progress_bar = st.progress(0, text="Analyzing articles...")

    for i, url in enumerate(final_urls_list):
        title, mentions, article_text = process_article(url, person_name)
        
        if article_text is None:
            unreadable_articles.append(url)
        else:
            summary = get_summary_from_gpt(article_text)
            sentiment = get_sentiment_from_gpt(person_name, mentions) if mentions else "No mentions found."
            results[url] = {'title': title, 'summary': summary, 'mentions': mentions, 'sentiment': sentiment}
        
        progress_bar.progress((i + 1) / len(final_urls_list), text=f"Analyzing: {url[:80]}...")
    
    progress_bar.empty()
    st.success("✅ Analysis Complete!")
    st.balloons()

    st.header("📊 Final Report", divider='rainbow')
    
    report_text_content = (
        f"News Mention, Summary & Sentiment Report\n=========================================\n"
        f"Person: {person_name}\nDate: {from_date.strftime('%A, %B %d, %Y')}\n\n"
    )

    if not results:
        st.warning("No articles could be successfully analyzed. They may have been empty or blocked access.")
    
    if results:
        report_text_content += "--- Analyzed Articles ---\n\n"
        for i, (url, data) in enumerate(results.items(), 1):
            with st.container(border=True):
                st.subheader(f"{i}. {data.get('title', 'Title Not Found')}", anchor=False)
                st.markdown(f"**Source:** [{url}]({url})")
                st.info(f"**AI Summary:** {data['summary']}")
                
                if "Positive" in data['sentiment']: st.success(f"**Sentiment:** {data['sentiment']}")
                elif "Negative" in data['sentiment']: st.error(f"**Sentiment:** {data['sentiment']}")
                else: st.warning(f"**Sentiment:** {data['sentiment']}")

                if data['mentions']:
                    with st.expander("Show mentions..."):
                        for sent in data['mentions']:
                            st.markdown(f'- "{sent}"')
            
            report_text_content += f"{i}. Title: {data.get('title', 'Title Not Found')}\n   URL: {url}\n\n   AI Summary: {data['summary']}\n\n   Sentiment Analysis: {data['sentiment']}\n"
            if data['mentions']:
                report_text_content += "   Mentions Found:\n"
                for sent in data['mentions']: report_text_content += f'   - "{sent}"\n'
            else:
                report_text_content += "   Mentions Found: None\n"
            report_text_content += "\n" + "="*50 + "\n\n"

    if recipient_email:
        with st.spinner("Preparing and sending email report..."):
            output_filename = f"Report-{person_name.replace(' ','_')}-{from_date.strftime('%Y-%m-%d')}.txt"
            with open(output_filename, "w", encoding='utf-8') as f:
                f.write(report_text_content)
            
            email_subject = f"News & Sentiment Report for {person_name} on {from_date.strftime('%Y-%m-%d')}"
            email_body = f"Hi,\n\nPlease find the attached news summary and sentiment report for {person_name} covering {from_date.strftime('%Y-%m-%d')}.\n\nBest wishes,\nKaitlyn's Robot Minion"
            
            if send_email_with_attachment(email_subject, email_body, recipient_email, output_filename):
                st.success(f"✅ Report successfully sent to {recipient_email}!")
            else:
                st.error("Failed to send the email report.")
            
            # Clean up the created file
            if os.path.exists(output_filename):
                os.remove(output_filename)

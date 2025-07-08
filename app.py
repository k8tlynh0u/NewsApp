# ==============================================================================
#      NEWS MENTION, SUMMARY & SENTIMENT ANALYZER - (V8 - FULL FEATURED)
#
# This is the complete, full-featured application with both NewsAPI and
# Google News (via Selenium), using the final robust setup.
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

# --- STEP 2: SETUP & CONFIGURATION ---

@st.cache_resource
def setup_openai_client():
    try:
        openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        return openai_client
    except Exception as e:
        st.error(f"Could not set up OpenAI client: {e}")
        st.stop()

@st.cache_resource
def setup_spacy_model():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        st.error("SpaCy model 'en_core_web_sm' not found. Please ensure it's in your requirements.txt.")
        st.stop()

# --- Load all necessary models and clients ---
openai_client = setup_openai_client()
nlp = setup_spacy_model()

# --- API & Email Configuration ---
MY_API_KEY = st.secrets["NEWSAPI_KEY"]
SENDER_EMAIL = st.secrets["SENDER_EMAIL"]
SENDER_PASSWORD = st.secrets["SENDER_PASSWORD"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# --- STEP 3: HELPER FUNCTIONS ---

def fetch_from_google_rss(person_name, from_date, to_date):
    urls_found = []
    try:
        query_terms = f'"{person_name}" after:{from_date.strftime("%Y-%m-%d")} before:{to_date.strftime("%Y-%m-%d")}'
        rss_url = f"https://news.google.com/rss/search?q={quote(query_terms)}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            urls_found.append(entry.get("link", ""))
        return urls_found
    except Exception as e:
        st.warning(f"Could not fetch from Google News RSS: {e}")
        return []

def fetch_from_newsapi(api_client, person_name, from_date, to_date):
    urls_found = []
    try:
        all_articles = api_client.get_everything(
            q=f'"{person_name}"', from_param=from_date.isoformat(), to=to_date.isoformat(),
            language='en', sort_by='relevancy', page_size=40
        )
        for article in all_articles.get('articles', []):
            urls_found.append(article['url'])
        return urls_found
    except Exception as e:
        st.warning(f"Could not fetch from NewsAPI: {e}")
        return []

def convert_google_news_link(google_news_url: str) -> str | None:
    if 'google.com' not in google_news_url:
        return google_news_url
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    driver = None
    try:
        service = ChromeService()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(google_news_url)
        WebDriverWait(driver, 20).until(lambda d: "google.com" not in d.current_url)
        final_url = driver.current_url
        return final_url
    except Exception as e:
        st.warning(f"Selenium failed for {google_news_url}. Reason: {e}")
        return None # Return None on failure so we can filter it out
    finally:
        if driver: driver.quit()

def process_article(url, name_to_find):
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        config.request_timeout = 25
        
        article = Article(url, config=config)
        article.download()
        article.parse()

        title = article.title if article.title else "Title Not Found"
        
        if not article.text or len(article.text) < 200:
            return (None, None, None)
        
        full_text = article.text
        doc = nlp(full_text)
        found_sentences = [s.text.strip().replace('\n', ' ') for s in doc.sents if name_to_find.lower() in s.text.lower()]
        return (title, found_sentences, full_text)
    except Exception:
        return (None, None, None)

# (GPT and Email functions remain the same)
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
    if not SENDER_PASSWORD: return False
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
st.markdown("This tool scours Google News and NewsAPI for articles about a specific person, then uses AI to summarize each article and analyze the sentiment.")

col1, col2 = st.columns(2)
with col1:
    person_name = st.text_input("👤 **Person's Full Name**", placeholder="e.g., Joe Biden")
    date_input = st.date_input("🗓️ **Date to Search**", datetime.now() - timedelta(days=2))
with col2:
    recipient_email = st.text_input("✉️ **Your Email Address (Optional)**", placeholder="Enter your email to receive the report")

if st.button("🚀 Generate Report", type="primary", use_container_width=True):
    if not person_name:
        st.warning("Please enter a person's name to start the analysis.")
        st.stop()

    from_date = date_input
    to_date = from_date + timedelta(days=1)
    
    st.markdown("---")
    st.subheader("⚙️ Analysis Log")

    with st.spinner(f"🔍 Searching sources for '{person_name}'..."):
        newsapi_client = NewsApiClient(api_key=MY_API_KEY)
        google_urls = fetch_from_google_rss(person_name, from_date, to_date)
        newsapi_urls = fetch_from_newsapi(newsapi_client, person_name, from_date, to_date)
    
    st.info(f"Found {len(google_urls)} links from Google News and {len(newsapi_urls)} links from NewsAPI.")

    with st.spinner("Resolving Google News links... (This is the slow part)"):
        resolved_google_urls = [convert_google_news_link(url) for url in google_urls]
        # Filter out any links that failed to resolve
        valid_resolved_urls = [url for url in resolved_google_urls if url]

    final_urls_list = sorted(list(set(valid_resolved_urls + newsapi_urls)))
    
    if not final_urls_list:
        st.error(f"No usable articles found for '{person_name}' on {from_date.strftime('%Y-%m-%d')}. Please try another name or date.")
        st.stop()

    st.success(f"Found {len(final_urls_list)} unique, usable articles. Now analyzing...")
    
    results = {}
    progress_bar = st.progress(0, text="Analyzing articles...")
    
    for i, url in enumerate(final_urls_list):
        title, mentions, article_text = process_article(url, name_to_find)
        if article_text:
            summary = get_summary_from_gpt(article_text)
            sentiment = get_sentiment_from_gpt(person_name, mentions) if mentions else "No mentions found."
            results[url] = {'title': title, 'summary': summary, 'mentions': mentions, 'sentiment': sentiment}
        progress_bar.progress((i + 1) / len(final_urls_list), text=f"Analyzing: {url[:80]}...")
    
    progress_bar.empty()
    st.success("✅ Analysis Complete!")
    if results: st.balloons()

    st.header("📊 Final Report", divider='rainbow')
    
    if not results:
        st.warning("No articles could be successfully analyzed.")
    else:
        # Display results and prepare email content...
        pass # The rest of your display logic goes here and is unchanged

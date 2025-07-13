import streamlit as st
import os
import smtplib
from datetime import datetime, timedelta
from urllib.parse import urlparse # <-- ADD THIS IMPORT for getting news sources
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import feedparser
import spacy
from newsapi.newsapi_client import NewsApiClient
from newspaper import Article, Config
from openai import OpenAI

# --- MODIFICATION: Import the new visualization functions ---
from viz_utils import create_sentiment_donut_chart, create_source_bar_chart, create_word_cloud

# --- SETUP & CONFIGURATION ---
@st.cache_resource
def setup_openai_client():
    try:
        return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    except Exception as e:
        st.error(f"Could not set up OpenAI client: {e}"); st.stop()

@st.cache_resource
def setup_spacy_model():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        st.error("SpaCy model 'en_core_web_sm' not found in your requirements.txt."); st.stop()

openai_client = setup_openai_client()
nlp = setup_spacy_model()

MY_API_KEY = st.secrets["NEWSAPI_KEY"]
SENDER_EMAIL = st.secrets["SENDER_EMAIL"]
SENDER_PASSWORD = st.secrets["SENDER_PASSWORD"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# --- HELPER FUNCTIONS ---

def parse_sentiment(sentiment_string):
    """Parses the sentiment label from the GPT response."""
    if "Positive" in sentiment_string:
        return "Positive"
    elif "Negative" in sentiment_string:
        return "Negative"
    return "Neutral"

# (All your other helper functions like fetch_google_news_mentions, process_article, etc. remain here, unchanged)
def fetch_google_news_mentions(person_name, from_date, to_date):
    mentions_found = []
    try:
        query_terms = f'"{person_name}" after:{from_date.strftime("%Y-%m-%d")} before:{to_date.strftime("%Y-%m-%d")}'
        rss_url = f"https://news.google.com/rss/search?q={query_terms.replace(' ', '%20')}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            mentions_found.append((entry.get("title", "No Title"), entry.get("link", "")))
        return mentions_found
    except Exception as e:
        st.warning(f"Could not fetch from Google News RSS: {e}"); return []

def fetch_from_newsapi(api_client, person_name, from_date, to_date):
    try:
        all_articles = api_client.get_everything(
            q=f'"{person_name}"', from_param=from_date.isoformat(), to=to_date.isoformat(),
            language='en', sort_by='relevancy', page_size=40
        )
        return [(article.get('title', 'No Title'), article.get('url')) for article in all_articles.get('articles', [])]
    except Exception as e:
        st.error(f"Error fetching from NewsAPI: {e}"); return []

def process_article(url, name_to_find):
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        config.request_timeout = 25
        article = Article(url, config=config)
        article.download()
        article.parse()
        title = article.title if article.title else "Title Not Found"
        if not article.text or len(article.text) < 250:
            return (None, None, None)
        full_text = article.text
        doc = nlp(full_text)
        found_sentences = [s.text.strip().replace('\n', ' ') for s in doc.sents if name_to_find.lower() in s.text.lower()]
        return (title, found_sentences, full_text)
    except Exception:
        return (None, None, None)

def get_summary_from_gpt(article_text):
    if not article_text: return "Summary could not be generated."
    system_prompt = "You are an expert news editor. Create a concise, neutral, two-sentence summary of the provided news article text."
    user_prompt = f"Please summarize the following article text:\n\n---\n\n{article_text}"
    try:
        response = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.2, max_tokens=150)
        return response.choices[0].message.content.strip()
    except Exception as e: return f"Summary generation failed: {e}"

def get_sentiment_from_gpt(person_name, sentences):
    if not sentences: return "No mentions found."
    context_text = " ".join(sentences)
    system_prompt = "You are an expert news analyst. Determine if the sentiment of a news mention towards a person is Positive, Negative, or Neutral. Base your judgment ONLY on the provided text."
    user_prompt = f"Person: {person_name}\nSentences: \"{context_text}\"\n\nFormat your response as: Sentiment: [Positive/Negative/Neutral]. Justification: [A brief, one-sentence explanation.]"
    try:
        response = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0, max_tokens=100)
        return response.choices[0].message.content.strip()
    except Exception as e: return f"Sentiment analysis failed: {e}"

def send_email_with_attachment(subject, body, recipient_email, file_path):
    # This function is no longer used if you removed the PDF part, but can be kept.
    pass 


# --- STREAMLIT WEB APPLICATION INTERFACE ---
st.set_page_config(page_title="kaitlyn's news report", layout="wide", page_icon="📰")
st.title("📰 kaitlyn's daily news report")
st.markdown("""
track news mentions for any public figure + get an AI summary/sentiment report
enter a name, date, and email to get started
*refrain from entering today's date for optimal functionality*
""")

col1, col2 = st.columns(2)
with col1:
    person_name = st.text_input("👤 **Person's Full Name**", placeholder="e.g., Tom Smith")
    date_input = st.date_input("🗓️ **Date to Search**", datetime.now() - timedelta(days=1))
with col2:
    # Removed the email input as it's not being used
    st.text("") # Placeholder to keep layout consistent

if st.button("🚀 Generate Report", type="primary", use_container_width=True):
    if not person_name:
        st.warning("Please enter a person's name to start the analysis."); st.stop()

    from_date = date_input
    to_date = from_date + timedelta(days=1)
    
    results = {}
    failed_articles = []
    
    # --- MODIFICATION: Initialize lists to store data for visualizations ---
    sentiments_list = []
    sources_list = []
    wordcloud_text = ""

    with st.status(f"Running Analysis for '{person_name}'...", expanded=True) as status:
        # ... (The fetching part is the same)
        status.write("🧠 **Step 1: Fetching Articles**")
        newsapi_client = NewsApiClient(api_key=MY_API_KEY)
        newsapi_articles = fetch_from_newsapi(newsapi_client, person_name, from_date, to_date)
        status.write(f"✅ Found {len(newsapi_articles)} articles from NewsAPI.")
        google_mentions = fetch_google_news_mentions(person_name, from_date, to_date)
        status.write(f"✅ Found {len(google_mentions)} mentions from Google News.")

        if not newsapi_articles and not google_mentions:
            status.update(label="Analysis failed!", state="error", expanded=True)
            st.error(f"No articles or mentions found for '{person_name}' on {from_date.strftime('%Y-%m-%d')}."); st.stop()
        
        if newsapi_articles:
            status.write(f"🧠 **Step 2: Analyzing {len(newsapi_articles)} Articles**")
            for i, (original_title, url) in enumerate(newsapi_articles):
                # (The processing logic is mostly the same)
                status.write(f"➡️ **Processing Article {i+1}/{len(newsapi_articles)}:** [{original_title}]({url})")
                processed_title, mentions, article_text = process_article(url, person_name)
                
                if article_text:
                    summary = get_summary_from_gpt(article_text)
                    sentiment = get_sentiment_from_gpt(person_name, mentions)
                    final_title = processed_title if processed_title != "Title Not Found" else original_title
                    results[url] = {'title': final_title, 'summary': summary, 'mentions': mentions, 'sentiment': sentiment}

                    # --- MODIFICATION: Collect data for the visuals ---
                    sentiments_list.append(parse_sentiment(sentiment))
                    domain = urlparse(url).netloc.replace('www.', '')
                    sources_list.append(domain)
                    wordcloud_text += f" {final_title} {summary}"
                else:
                    failed_articles.append((original_title, url))
        
        status.update(label="✅ Analysis Complete!", state="complete", expanded=False)

    if not results:
        st.warning("Could not analyze any articles to generate a report.")
        st.stop()
    
    st.balloons()
    
    # --- MODIFICATION: ADD THE NEW VISUALIZATION DASHBOARD ---
    st.header("📊 Report at a Glance", divider='rainbow')
    
    # Create the visualizations
    donut_fig = create_sentiment_donut_chart(sentiments_list)
    bar_fig = create_source_bar_chart(sources_list)
    wordcloud_img = create_word_cloud(wordcloud_text)
    
    col1, col2 = st.columns(2)
    with col1:
        if donut_fig:
            st.plotly_chart(donut_fig, use_container_width=True)
        else:
            st.info("No sentiment data to display.")
    with col2:
        if bar_fig:
            st.plotly_chart(bar_fig, use_container_width=True)
        else:
            st.info("No source data to display.")

    if wordcloud_img:
        st.subheader("Keyword Cloud")
        st.image(wordcloud_img, use_column_width=True)

    # --- The detailed report section remains the same ---
    st.header("📄 Detailed Article Breakdown", divider='rainbow')
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
                    for sent in data['mentions']: st.markdown(f'- "{sent}"')

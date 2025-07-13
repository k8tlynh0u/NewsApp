import pandas as pd
import plotly.express as px
from wordcloud import WordCloud
import matplotlib.pyplot as plt

def create_sentiment_donut_chart(sentiments_list):
    """Creates a donut chart from a list of sentiment labels."""
    if not sentiments_list:
        return None

    # Count the occurrences of each sentiment
    sentiment_counts = pd.Series(sentiments_list).value_counts()
    
    # Define colors to match Streamlit's theme
    colors = {
        'Positive': 'green',
        'Negative': 'red',
        'Neutral': 'orange'
    }
    
    fig = px.pie(
        sentiment_counts,
        values=sentiment_counts.values,
        names=sentiment_counts.index,
        title="Sentiment Breakdown",
        hole=0.4, # This creates the donut shape
        color=sentiment_counts.index,
        color_discrete_map=colors
    )
    fig.update_traces(textinfo='percent+label', pull=[0.05, 0.05, 0.05])
    return fig

def create_source_bar_chart(sources_list):
    """Creates a horizontal bar chart of article sources."""
    if not sources_list:
        return None

    source_counts = pd.Series(sources_list).value_counts().sort_values(ascending=True)
    
    fig = px.bar(
        source_counts,
        x=source_counts.values,
        y=source_counts.index,
        orientation='h',
        title="Top News Sources",
        labels={'x': 'Number of Articles', 'y': 'Source'}
    )
    fig.update_layout(showlegend=False)
    return fig

def create_word_cloud(text):
    """Generates and returns a word cloud image from a block of text."""
    if not text:
        return None
        
    # Generate a word cloud image
    wordcloud = WordCloud(
        width=800, 
        height=400, 
        background_color='white',
        colormap='viridis',
        collocations=False # Avoids grouping common word pairs
    ).generate(text)
    
    # We return the image itself to be displayed in Streamlit
    return wordcloud.to_image()

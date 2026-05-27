import requests
from bs4 import BeautifulSoup
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.stem import PorterStemmer
import json
import logging

nltk.download('punkt')
nltk.download('stopwords')

class NewsAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = 'https://newsapi.org/v2/everything'

    def fetch_articles(self, params=None):
        if params is None:
            params = {}
        headers = {'Authorization': f'Bearer {self.api_key}'}
        response = requests.get(self.base_url, params=params, headers=headers)
        return response.json()

    def summarize_article(self, article):
        text = article['articleContent']
        soup = BeautifulSoup(text, 'html.parser')
        text = soup.get_text()
        sentences = sent_tokenize(text)
        stop_words = set(stopwords.words('english'))
        stemmer = PorterStemmer()
        summary = []
        for sentence in sentences:
            tokens = word_tokenize(sentence.lower())
            tokens = [stemmer.stem(token) for token in tokens if token.isalpha() and token not in stop_words]
            if len(tokens) > 3:
                summary.append(' '.join(tokens))
        return ' '.join(summary)

    def summarize(self, article):
        return self.summarize_article(article)
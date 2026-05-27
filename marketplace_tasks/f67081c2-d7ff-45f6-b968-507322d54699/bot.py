import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer
import string
import re

nltk.download('punkt')
nltk.download('stopwords')

class NewsBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = 'YOUR_BOT_TOKEN'
        self.stop_words = set(stopwords.words('english'))

    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')

    @commands.command()
    async def summarize(self, ctx, url: str):
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()

            # Remove special characters and numbers
            text = re.sub(r'[^a-zA-Z\s]', '', text)

            # Tokenize the text
            tokens = word_tokenize(text.lower())

            # Remove stop words
            filtered_tokens = [token for token in tokens if token not in self.stop_words]

            # Stem the tokens
            stemmer = PorterStemmer()
            stemmed_tokens = [stemmer.stem(token) for token in filtered_tokens]

            # Join the stemmed tokens back into a string
            summary = ' '.join(stemmed_tokens)

            await ctx.send(summary)
        except Exception as e:
            await ctx.send('Error: ' + str(e))

bot = NewsBot()
bot.run(self.token)
import discord
from discord.ext import commands
from newsapi import NewsApiClient
from newsapi.models import Article

class NewsBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.news_api_client = NewsApiClient(api_key='YOUR_API_KEY')

    @commands.command()
    async def summarize(self, ctx, url: str):
        try:
            article = self.news_api_client.get_article(url)
            summary = article['description']
            await ctx.send(summary)
        except Exception as e:
            await ctx.send(f"Failed to retrieve news: {str(e)}")

def setup(bot):
    bot.add_cog(NewsBot(bot))
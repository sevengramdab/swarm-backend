import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.stem import PorterStemmer
from collections import defaultdict
from heapq import nlargest
import re

class Summarizer:
    def __init__(self):
        self.stop_words = set(stopwords.words('english'))
        self.stemmer = PorterStemmer()

    def summarize(self, text, num_sentences=5):
        sentences = sent_tokenize(text)
        word_counts = defaultdict(int)

        for sentence in sentences:
            words = word_tokenize(sentence.lower())
            for word in words:
                if word not in self.stop_words and re.match('^[a-zA-Z]', word):
                    word = self.stemmer.stem(word)
                    word_counts[word] += 1

        sentence_scores = defaultdict(int)
        for sentence in sentences:
            for word, count in word_counts.items():
                if word in sentence.lower():
                    sentence_scores[sentence] += count

        top_sentences = nlargest(num_sentences, sentence_scores, key=sentence_scores.get)

        summary = ' '.join(top_sentences)
        return summary


def main():
    summarizer = Summarizer()
    text = """The 2020 COVID-19 pandemic is a global health crisis caused by the SARS-CoV-2 virus. The World Health Organization (WHO) declared it a Public Health Emergency of International Concern on January 30, 2020.
The virus was first detected in Wuhan, China in December 2019. It has since spread to every region of the world, infecting millions of people and causing widespread illness and death.
The pandemic has had a significant impact on the global economy, with many countries imposing lockdowns and travel restrictions to slow the spread of the virus.
The WHO has declared that the pandemic is a global health crisis, and has called for international cooperation to combat it."""

    print(summarizer.summarize(text))


if __name__ == "__main__":
    main()
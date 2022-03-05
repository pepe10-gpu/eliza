from shimeji import ChatBot
from shimeji.preprocessor import ContextPreprocessor
from shimeji.postprocessor import NewlinePrunerPostprocessor

from core.logging import get_logger

import tweepy

logger = get_logger(__name__)

class Bot:
    def __init__(self, name, model_provider, **kwargs):
        self.name = name
        self.model_provider = model_provider
        self.kwargs = kwargs
    
    def run(self):
        raise NotImplementedError
    

class TerminalBot(Bot):
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        self.chatbot = ChatBot(
            name=self.name,
            model_provider=self.model_provider,
            preprocessors=[ContextPreprocessor()],
            postprocessors=[NewlinePrunerPostprocessor()]
        )
    
    def run(self):
        while True:
            try:
                user_input = input('User: ')
                response = self.chatbot.respond(f'User: {user_input}', push_chain=True)
                print(f'{self.name}:{response}')
            except KeyboardInterrupt:
                print('Exiting...')
                break

class TwitterBot(Bot):
    def __init__(self, name, model_provider, **kwargs):
        # essentially a callback-like thing for TwitterClient
        super().__init__(name, model_provider,  **kwargs)
        self.kwargs = kwargs

        self.chatbot = ChatBot(
            name=self.name,
            model_provider=model_provider,
            preprocessors=[ContextPreprocessor()],
            postprocessors=[NewlinePrunerPostprocessor()]
        )

        self.client = tweepy.StreamingClient(
            bearer_token=self.kwargs['bearer_token']
        )

        self.auth = tweepy.OAuthHandler(
            self.kwargs['consumer_key'],
            self.kwargs['consumer_secret']
        )

        self.client_api = tweepy.Client(
            bearer_token=self.kwargs['bearer_token'],
            consumer_key=self.kwargs['consumer_key'],
            consumer_secret=self.kwargs['consumer_secret'],
            access_token=self.kwargs['access_token'],
            access_token_secret=self.kwargs['access_token_secret'],
            wait_on_rate_limit=True
        )

        self.expansions = ["referenced_tweets.id", "author_id"]
        self.user_fields = ["name"]

        # add rule to check if user is talking to the bot
        self.client.add_rules(
            [
                tweepy.StreamRule(f'to:{self.kwargs["username"]}')
            ]
        )
        self.client.on_tweet = self.on_tweet
    
    # tweet helper
    def tweet(self, text, reply_to=None):
        if reply_to:
            self.client_api.create_tweet(
                text=text,
                in_reply_to_tweet_id=reply_to
            )
        else:
            self.client_api.create_tweet(text=text)
    
    # return a list of strings that are the conversational history of a tweet
    def get_conversation(self, id):
        conversation = []
        tweet = self.client_api.get_tweet(id, expansions=self.expansions, user_fields=self.user_fields)
        
        for user in tweet.includes['users']:
            author = user['name']
        
        conversation.append(f"{author}: {tweet.data.text}")
        if 'tweets' in tweet.includes:
            for tweet_id in tweet.includes['tweets']:
                # prepend parent tweet to conversation, since get_conversation returns an array, expand it
                conversation.insert(0, self.get_conversation(tweet_id.id)[0])
        
        return conversation
    
    # on_tweet: check if tweet is in reply to bot, if it is, get the conversation and respond
    def on_tweet(self, tweet):
        logger.info(f'Tweet received: {tweet.id}')
        conversation = self.get_conversation(tweet.id)
        response = self.chatbot.respond('\n'.join(conversation), push_chain=False)
        self.tweet(response, reply_to=tweet.id)

    def run(self):
        self.client.filter(expansions=self.expansions, user_fields=self.user_fields)

import snscrape.modules.twitter as twitterScraper
import pandas as pd
import schedule
import tweepy
import json
import pickle
import os
from datetime import datetime as dt
from datetime import timedelta
import pytz
import time
import random
import functools
import cleantext
import requests
import openai
import praw

from newsapi import NewsApiClient

news_api = NewsApiClient(api_key=open('newsapi_key', 'r').read())


def connect_app_to_twitter(config):
    auth = tweepy.OAuthHandler(config.get('DEFAULT', 'api_key'), config.get('DEFAULT', 'api_secret'))
    auth.set_access_token(config.get('DEFAULT', 'access_token'), config.get('DEFAULT', 'access_token_secret'))
    api = tweepy.API(auth)
    return api


def ask_openai(prompt):
    print(prompt)
    key = open('openai_key', 'r').read()
    openai.api_key = key

    #    prompt = "write a fascinated tweet on a newly tested ai service for bitcoin price discovery"

    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        temperature=0.6,
        max_tokens=60
    )
    return response.choices[0]['text']


def api_check_sentiment(text):
    url = "https://twinword-sentiment-analysis.p.rapidapi.com/analyze/"
    querystring = {
        "text": text}
    headers = {
        "X-RapidAPI-Key": "f7840680cfmsh06caa5664044614p1ce717jsnac7cbe48fa53",
        "X-RapidAPI-Host": "twinword-sentiment-analysis.p.rapidapi.com"
    }
    response = requests.request("GET", url, headers=headers, params=querystring)
    return json.loads(response.content)['type']


class Book(object):
    def __init__(self, account_name):
        self.book_path = account_name + '.pcl'
        if os.path.exists(self.book_path):
            self.book = pickle.load(open(self.book_path, 'rb'))
        else:
            self.book = dict()

    def n_entries(self):
        return len(self.book.keys())

    def store_update_book(self):
        pickle.dump(self.book, open(self.book_path, 'wb'))

    def add(self, action, tweet, action2='', user_id=-1):
        timestamp = int(time.time())
        if tweet is not None:
            self.book[timestamp] = {'action': action, 'tweet_id': tweet['tweet_id'],
                                    'text': tweet['text'],
                                    'username': tweet['username'], 'action2': action2, 'tweet': tweet,
                                    'user_id': tweet['user_id']}
        else:
            self.book[timestamp] = {'action': action, 'tweet_id': '', 'text': '',
                                    'username': '', 'action2': action2, 'tweet': '', 'user_id': user_id}
        self.store_update_book()

    def as_df(self):
        book_df = pd.DataFrame(self.book).T
        book_df['timestamp'] = pd.to_datetime(book_df.index, unit='s')
        if book_df.shape[0] > 0:
            return book_df
        else:
            return pd.DataFrame(columns=['action', 'tweet_id', 'text', 'username', 'action2', 'tweet', 'user_id'])

    def n_items(self):
        return len(self.book)


class Bot(object):
    book: Book

    def __init__(self, config):
        self.config = config
        self.account_name = self.config.get('DEFAULT', 'account_name')
        self.blacklist = json.loads(self.config.get('DEFAULT', 'blacklist'))
        self.keywords = json.loads(self.config.get('DEFAULT', 'keywords'))
        self.keywords = [x.lower() for x in self.keywords]
        self.secondary_keywords = json.loads(self.config.get('DEFAULT', 'secondary_keywords'))
        self.hashtags = json.loads(self.config.get('DEFAULT', 'hashtags'))
        self.book = Book(account_name=self.account_name)
        self.friends = json.loads(self.config.get('DEFAULT', 'friends'))
        self.api = connect_app_to_twitter(config)
        self.tweets_df = None
        self.news = {}

        self.n_favorites = 0
        self.n_tweets_per_day = 0
        self.n_follows_per_day = 0
        self.n_replys_per_day = 0
        self.n_directs_per_day = 0
        self.n_retweets_per_day = 0

        self.reddit = None
        try:
            self.reddit = praw.Reddit(
                client_id=self.config.get('DEFAULT', 'reddit_id'),
                client_secret=self.config.get('DEFAULT', 'reddit_secret'),
                username=self.config.get('DEFAULT', 'reddit_username'),
                password=self.config.get('DEFAULT', 'reddit_password'),
                user_agent=self.config.get('DEFAULT', 'reddit_agent'),
            )
        except:
            pass

    def post_on_reddit(self, title, text):
        try:
            subreddit = self.reddit.subreddit("valleytalk")
            subreddit.submit(title=title, selftext=text)
        except:
            pass

    def is_text_blocked_by_blacklist(self, text):
        blacklist = json.loads(self.config.get('DEFAULT', 'blacklist'))
        for item in blacklist:
            if item.lower() in text.lower():
                return True
        return False

    def is_tweet_blocked_by_blacklist(self, tweet):
        return self.is_text_blocked_by_blacklist(tweet.content)

    @staticmethod
    def is_blocked_by_actuality(tweet):
        publish_date = tweet.date
        if publish_date < dt.now(pytz.utc) - timedelta(hours=1):
            return True
        return False

    @staticmethod
    def is_blocked_by_content(tweet):
        text = tweet.content
        if text.startswith('@'):
            return True
        if text.startswith('RT'):
            return True
        if text.count('@') > 1:
            return True
        if text.count('#') > 3:
            return True
        if text.count('!') > 1:
            return True
        if text.count('?') > 1:
            return True
        return False

    def favoriter(self):
        self.tweets_df = self.tweets_df.sample(frac=1)

        for i, tweet in self.tweets_df.iterrows():
            text = tweet['text']
            if self.is_text_blocked_by_blacklist(text):
                continue
            success_count, secondary_success_count = self.success_metrics(text)
            #                success_count += sum([' ' + word + ' ' in description for word in self.keywords])
            if success_count == 0:
                continue
            if success_count + secondary_success_count < 1.5:
                continue
            if api_check_sentiment(text) != 'positive':
                continue
            book_df = self.book.as_df()
            if tweet['text'] in book_df.query('action == "favorite"')['text'].values:
                continue
            try:
                self.api.create_favorite(id=str(tweet['tweet_id']))
                self.book.add(action='favorite', tweet=tweet)
            except tweepy.errors.Forbidden:
                pass
            except Exception as e:
                print('Exception in favorite')
                print(e)
                continue
            return

    def reply_tweet(self, tweet):
        # Check if tweet was already replied to, in this case, just skip it

        keyword = tweet['keyword'].lower()
        tweet_id = tweet['tweet_id']

        answers = [
            'interesting read!',
            'keep going!',
            'food for thought!',
            'more on this, pls!',
            'great insights!',
            'good summary!',
            'good to read!'

        ]

        print('sending reply to %s %s' % (tweet['tweet_url'], tweet['tweet_id']))

        hashtags = ' #' + ' #'.join([random.choice(self.hashtags) for i in range(2)])

        answer_text = ask_openai(
            'write a smart and thoughtful twitter reply for me with a maximum of three very common hashtags to the following tweet: %s' %
            tweet['text'])
        try:
            # reply = random.choice(answers) + ' #%s' % keyword + hashtags
            self.api.update_status(status=answer_text,
                                   in_reply_to_status_id=tweet_id,
                                   auto_populate_reply_metadata=True)
            self.book.add(action='reply', tweet=tweet)
        except Exception as e:
            print('Exception in reply')
            print(e)

    def replyer(self):
        self.tweets_df = self.tweets_df.sample(frac=1)
        for i, tweet in self.tweets_df.iterrows():
            tweet_id = tweet['tweet_id']
            tweet_was_already_replied = self.book.as_df().query("(action=='reply') & (tweet_id==@tweet_id)").shape[0]
            if tweet_was_already_replied > 0:
                continue
            success_sum, secondary_success_sum = self.success_metrics(tweet['text'])
            if success_sum < 1 or secondary_success_sum + success_sum < 2:
                continue
            self.reply_tweet(tweet)
            return

    def direct_message(self, tweet):
        book_df = self.book.as_df()
        book_df = book_df[book_df['action'] == 'direct']
        if book_df.shape[0] > 0:
            users_with_directs = book_df['username'].values
            if tweet['username'] in users_with_directs:
                return
        texts = [
            'I like your content, happy to be in touch!',
            'Great content! Happy to be connected.',
            'Great to be in touch! Can you tell me more about you?',
            'I like your content. Can I read more about you?'
        ]
        try:
            self.api.send_direct_message(recipient_id=tweet['user_id'], text=random.choice(texts))
            print('sending direct message')
            self.book.add(action='direct', tweet=tweet)
        except tweepy.errors.Forbidden:
            time.sleep(5)
        except Exception as e:
            print('Exception in direct message')
            print(e)
            time.sleep(5)

    def directs(self):
        self.tweets_df = self.tweets_df.sample(frac=1)
        n_max = 5
        count = 0

        for row in self.tweets_df.iterrows():
            tweet = row[1]
            self.direct_message(tweet)

            count += 1
            time.sleep(3)
            if count >= n_max:
                break

    def unfollower(self):
        n_max = 10
        follower_ids = [user.id for user in self.api.get_followers()]
        friend_ids = self.api.get_friend_ids()

        count = 0
        for fid in friend_ids:
            if fid not in follower_ids:
                self.api.destroy_friendship(user_id=fid)
                self.book.add(action='unfollow', tweet=None, user_id=fid)
                print('unfollow', fid)
                time.sleep(5)
                count += 1
                if count >= n_max:
                    return

    def follower(self):
        # Take Care of unfollower
        # self.unfollower()
        self.tweets_df = self.tweets_df.sample(frac=1)

        n_max = 5
        count = 0

        for row in self.tweets_df.iterrows():
            if count >= n_max:
                return
            book_df = self.book.as_df()
            tweet = row[1]
            username = tweet['username']
            user_id = tweet['user_id']
            if self.is_text_blocked_by_blacklist(tweet['user_description']):
                continue
            success_rate, secondary_success_rate = self.success_metrics(tweet['user_description'])
            if success_rate < 1:
                continue
            print(username)

            # do not double-add users - a user get's never double added
            # if username in book_df[book_df['action'] == 'follow']['username']:
            #    continue

            # the earliest time a user gets double added is after 10 days
            unfollowed_ids = book_df[book_df['action'] == 'unfollow']['user_id'].values
            if user_id in unfollowed_ids:
                timestamp_unfollow = book_df[book_df['user_id'] == user_id]['timestamp'].values[0]
                if pd.Timestamp.now() - timestamp_unfollow < timedelta(hours=10 * 24):
                    continue
            followed_ids = book_df[book_df['action'] == 'follow']['user_id'].values

            # if user was followed within the past 10 days, don't try to follow again
            if user_id in followed_ids:
                timestamp_follow = book_df[book_df['user_id'] == user_id]['timestamp'].values[0]
                if pd.Timestamp.now() - timestamp_follow < timedelta(hours=10 * 24):
                    continue

            try:
                self.api.create_friendship(screen_name=username)
                self.book.add(action='follow', tweet=tweet)
                count += 1
            except Exception as e:
                print('Error in Follower')
                print(e)
            time.sleep(5)

    def fill_news(self, keyword):
        # Fill the news based on a keyword. For each keyword there will be news.
        if keyword not in self.news:
            self.news[keyword] = {}
        self.news[keyword]['last_date'] = dt.now()
        try:
            self.news[keyword]['news'] = pd.DataFrame(news_api.get_everything(keyword)['articles'])
            return 0
        except Exception as e:
            print('fill news')
            time.sleep(5)
            print(e)
            return -1

    def success_metrics(self, content):
        content = content.lower()
        success_content = [{word: word in content} for word in self.keywords]
        success_count = sum([word in content for word in self.keywords])
        secondary_success_count = 0.5 * sum([word in content for word in self.secondary_keywords])
        return success_count, secondary_success_count

    def tweeter(self):
        random.shuffle(self.keywords)
        for keyword in self.keywords:
            if keyword in self.news:
                # if the keyword is found in news but is outdated, reload it otherwise use it
                if self.news[keyword]['last_date'] < dt.now() - timedelta(hours=24):
                    status = self.fill_news(keyword=keyword)
            else:
                status = self.fill_news(keyword=keyword)
                if status == -1:
                    print('News collection for keyword "%s" not successful' % keyword)

            for i, pub in self.news[keyword]['news'].sample(frac=1).iterrows():
                content = pub['content'].lower()
                description = pub['description'].lower()
                title = pub['title'][:240]
                # Check if news violate the blacklist
                for item in self.blacklist:
                    if item in content:
                        continue
                    if item in description:
                        continue
                    if item in title:
                        continue

                # Check if news are sufficiently relevant by demanding at least two keyword in the content
                # use the blanks in word to make sure it's the exact word and not just part of a largert bit.
                # as ai in Taiwan but x ai y
                success_count, secondary_success_count = self.success_metrics(content)
                #                success_count += sum([' ' + word + ' ' in description for word in self.keywords])
                if success_count == 0:
                    continue
                if success_count + secondary_success_count < 2:
                    continue

                url = pub['url']
                text = title + ' %s ' % url + ' #%s' % keyword.replace(' ', '')
                book_df = self.book.as_df()
                # check if tweet was already sent out

                # check if this news was already tweeted
                if title in book_df['action2'].values:
                    continue
                tweet_with_no_link = ask_openai(
                    'Write a smart and thoughtful tweet for me with a maximum of three very common hashtags based on the following text: %s' % content)

                self.post_on_reddit(title=title, text=url)

                if tweet_with_no_link == '':
                    print('content that raised exception')
                    print(content)
                try:
                    tweet = self.api.update_status(status=text)
                    self.book.add(action='tweet', tweet=None, action2=title)
                    time.sleep(10)

                    self.api.update_status(status=tweet_with_no_link, in_reply_to_status_id=tweet.id,
                                           auto_populate_reply_metadata=True)

                except Exception as e:
                    print('tweeter')
                    print(e)
                    print(tweet_with_no_link, '#', type(tweet_with_no_link))
                    print('Exception in send status')
                # end the double-loop when a matching tweet is found
                return 0

    def get_current_content(self, load_from_dump=False, drop_dump=False):
        if load_from_dump:
            if not os.path.exists('content_dump.pcl'):
                raise AttributeError('No Content Dump File conten_dump.pcl. Revise your setting "load_from_dump".')
            self.tweets_df = pickle.load(open('content_dump.pcl', 'rb'))
            df = self.tweets_df
            df['success_metric1'] = df['text'].map(lambda x: self.success_metrics(x)[0])
            df['success_metric2'] = df['text'].map(lambda x: self.success_metrics(x)[1])
            df[['keyword', 'text', 'success_metric1', 'success_metric2']].to_excel('tweets.xlsx')
            return 0
        tweets = []
        limit = 500
        today_date = dt.today().date().__str__()
        random.shuffle(self.keywords)
        for keyword in self.keywords:
            query = '"%s" min_faves:1 lang:en since:%s' % (keyword, today_date)
            count = 0
            try:
                scraper = twitterScraper.TwitterSearchScraper(query)
            except Exception as e:
                print('Exception in get_current_content')
                print(e)
                return -1
            for tweet in scraper.get_items():
                if self.is_tweet_blocked_by_blacklist(tweet):
                    continue
                if self.is_blocked_by_actuality(tweet):
                    continue
                if self.is_blocked_by_content(tweet):
                    continue
                # Filter out tweets with images or videos
                if tweet.media is not None:
                    continue
                if keyword.lower() not in tweet.content.lower():
                    continue
                tweets.append({
                    'keyword': keyword,
                    'date': tweet.date,
                    'text': tweet.content,
                    'username': tweet.user.username,
                    'tweet_id': tweet.id,
                    'user_description': tweet.user.description,
                    'user_followers': tweet.user.followersCount,
                    'user_id': tweet.user.id,
                    'user_obj': tweet.user,
                    'tweet_url': tweet.url
                })
                count += 1
                if count >= limit:
                    break
        if len(tweets) == 0:
            return -1

        df = pd.DataFrame(tweets)
        try:
            df['date'] = df['date'].map(lambda x: x.replace(tzinfo=None))
        except Exception as e:
            print('Exception in get_current_content')
            print(e)
        df['success_metric1'] = df['text'].map(lambda x: self.success_metrics(x)[0])
        df['success_metric2'] = df['text'].map(lambda x: self.success_metrics(x)[1])
        df.to_excel('tweets.xlsx')
        self.tweets_df = df
        if drop_dump:
            pickle.dump(self.tweets_df, open('content_dump.pcl', 'wb'))
        return 0

    def retweeter(self):
        pass

    def look_after_friends(self):
        # block followers with a link that contains "cams" to prevent cam girls
        followers = self.api.get_followers()
        count = 0
        for follower in followers:

            if follower.url is not None and \
                    (
                            'cams' in follower.entities['url']['urls'][0]['expanded_url'] or
                            'girls' in follower.entities['url']['urls'][0]['expanded_url'] or
                            'flirt' in follower.entities['url']['urls'][0]['expanded_url'] or
                            'free' in follower.entities['url']['urls'][0]['expanded_url'] or
                            'women' in follower.entities['url']['urls'][0]['expanded_url'] or
                            'babes' in follower.entities['url']['urls'][0]['expanded_url'] or
                            'celeb' in follower.entities['url']['urls'][0]['expanded_url']
                    ):
                count += 1
                print('remove ', follower.screen_name)
                self.api.create_block(screen_name=follower.screen_name)
                time.sleep(3)
                if count >= 10:
                    break

        # ToDo make sure friends get not unfriended
        random.shuffle(self.friends)
        for friend in self.friends:
            print("Taking care of friend", friend)
            user = self.api.get_user(screen_name=friend)
            try:
                timeline = self.api.user_timeline(screen_name=friend)
            except tweepy.errors.Unauthorized:
                continue
            random.shuffle(timeline)
            count = 0
            for element in timeline:
                if element.lang != 'en':
                    continue
                if element.text.startswith('RT'):
                    continue
                if element.text.startswith('@'):
                    continue
                success_metric = sum(self.success_metrics(element.text))
                if success_metric < 1.5:
                    continue

                count += 1
                if count > 5:
                    print('Count over 5 was achieded')
                    return
                try:
                    answer_text = ask_openai(
                        'write a smart and thoughtful twitter reply for me with a maximum of three very common hashtags to the following tweet: %s' % element.text)
                    self.api.update_status(status=answer_text,
                                           in_reply_to_status_id=element.id,
                                           auto_populate_reply_metadata=True)
                    self.book.add(action='friend_reply', tweet=None, action2=element.text)
                    print('created AI reply')
                    return 0
                except tweepy.errors.Forbidden:
                    print('Failed AI Reply')
                    return 0
                except Exception as e:
                    print('Exception in reply in look after friends')
                    print(e)
                    print('Failed AI Reply')
                try:
                    self.api.create_favorite(element.id)
                    print('created favorite')
                    return 0
                except tweepy.errors.Forbidden:
                    print('failed favorite')
                    time.sleep(2)
                try:
                    self.api.retweet(element.id)
                    print('created retweet')
                    return 0
                except tweepy.errors.Forbidden:
                    print('Failed retweet')
                    time.sleep(2)

    def run(self, random_sleep_at_start=True):
        if random_sleep_at_start:
            time.sleep(random.randint(1, 300))
        print(dt.now())
        look_after_friends = self.config.getint('DEFAULT', 'look_after_friends')
        if look_after_friends > 0:
            self.look_after_friends()
            time.sleep(3)
        status = self.get_current_content()
        if status == -1:
            return
        print('starting into interactions')
        r = random.randint(0, 24)
        self.n_favorites = self.config.getint('DEFAULT', 'favorites_per_day')
        if self.n_favorites > 0 and r <= self.n_favorites:
            print('run favoriter')
            self.favoriter()
            time.sleep(3)
        else:
            print('Favoriter not chosen', r, self.n_favorites)
        self.n_tweets_per_day = self.config.getint('DEFAULT', 'tweets_per_day')
        r = random.randint(0, 24)
        if self.n_tweets_per_day > 0 and r <= self.n_tweets_per_day:
            print('running tweeter')
            self.tweeter()
            time.sleep(3)
        else:
            print('Tweeter not chosen', r)
        self.n_follows_per_day = self.config.getint('DEFAULT', 'follows_per_day')
        if self.n_follows_per_day > 0:
            self.follower()
            time.sleep(3)
        else:
            print('Follower not chosen')
        self.n_replys_per_day = self.config.getint('DEFAULT', 'replys_per_day')
        if self.n_replys_per_day > 0 and random.randint(1, 24) <= self.n_replys_per_day:
            self.replyer()
            time.sleep(3)
        else:
            print('Replyer not chosen')

        self.n_directs_per_day = self.config.getint('DEFAULT', 'directs_per_day')
        if self.n_directs_per_day > 0 and random.randint(1, 24) <= self.n_directs_per_day:
            self.directs()
            time.sleep(3)
        self.n_retweets_per_day = self.config.getint('DEFAULT', 'retweets_per_day')
        if self.n_retweets_per_day > 0 and random.randint(1, 24) <= self.n_retweets_per_day:
            self.retweeter()
            time.sleep(3)

        print('waiting for next round ... ', dt.utcnow(), self.account_name)

    def run_scheduled(self):
        schedule.every(1).hour.do(self.run)
        while True:
            schedule.run_pending()

import random

from twitterBot.bot import Bot
import configparser
import time
import tweepy

config = configparser.RawConfigParser()
config.read('config2.ini')

bot = Bot(config)

followers = []

count = 0
for page in tweepy.Cursor(bot.api.get_friends,
                          count=200).pages(1000):
    count += 1
    # skip the first page these are the new follows
    if count == 1:
        continue

    for user in page:
        friendship_status = bot.api.lookup_friendships(screen_name=[user.screen_name])
        follows_me = friendship_status[0].is_followed_by
        if not follows_me:
            try:
                bot.api.destroy_friendship(screen_name=user.screen_name)
                print('Destroyed Friendship with %s' % user.screen_name)
                time.sleep(10 * 60 + random.randint(100, 500))

                if random.randint(1, 4) == 4:
                    time.sleep(60 * 60)

            except Exception as e:
                print(e)

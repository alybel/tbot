from daily_btc_update import *
from twitterBot.bot import Bot
import configparser
import sys
import time

config = configparser.RawConfigParser()
config.read('config3.ini')

bot = Bot(config)

if __name__ == '__main__':
    production = True
    if production:
        intraday_update = get_daily_update()
        with open('text.txt', 'w') as f:
            f.write(intraday_update)

        intraday_image = get_daily_image()
        disclaimer = 'This is not financial advise and the presented analysis can contain errors to which the producer can not be held accountable. Markets are not predictable. Always conduct your own research before making investment decisions. '


    else:
        intraday_update = open('text.txt', 'r').read()

    word_str = intraday_update.split(' ')
    print(word_str)
    tweet_str = ''
    tweet = bot.api.update_status_with_media(filename='plot.png',
                                             status='Daily 24-hour #BTC Forecast from Icecubeanalytics #crypto #intraday')
    time.sleep(2)
    tweet_bits = []
    for word in word_str:
        if len(tweet_str) < 200:
            tweet_str += ' ' + word
        else:
            tweet_str += ' ' + word
            print(tweet_str)
            tweet_bits.append(tweet_str)

            tweet_str = ''
    if len(tweet_str) > 0:
        tweet_bits.append(tweet_str)


    if production:
        for subtweet in tweet_bits:
            tweet = bot.api.update_status(status=subtweet, in_reply_to_status_id=tweet.id,
                                      auto_populate_reply_metadata=True)
            time.sleep(2)

    bot.api.update_status(status=disclaimer, in_reply_to_status_id=tweet.id,
                          auto_populate_reply_metadata=True)

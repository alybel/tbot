from twitterBot.bot import Bot
import configparser
import argparse
import time



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', metavar='-f', type=str, nargs=1,
                    help='an integer for the accumulator')
    args = parser.parse_args()
    

    config = configparser.RawConfigParser()
    config.read(args.f[0])

    bot = Bot(config)
    # run once without random sleep at start but then the next iterations such that the algo is not so obviously on a time grid
    bot.run(random_sleep_at_start=False)
    time.sleep(5)
    bot.run_scheduled()

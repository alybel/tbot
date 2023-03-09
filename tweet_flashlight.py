from twitterBot.bot import Bot
import streamlit as st
import time
import configparser
import sys

lead_config = configparser.RawConfigParser()
lead_config.read('config.ini')

lead_bot = Bot(lead_config)

st.write('Write the tweet you want to flashlight in the below textbox')
status = st.text_area(label='tweet_input')

filename = st.text_input(label='filename of picture')

button = st.button(label='Submit to Twitter')
button_stop = st.button(label='Stop the Action')

if button:
    while button and not button_stop:

        if filename != '':
            tweet_status = lead_bot.api.update_status_with_media(status=status, filename=filename)
        else:
            tweet_status = lead_bot.api.update_status(status=status)

        st.write('Postet! %d' % tweet_status.id)

        time.sleep(30*60)
        lead_bot.api.destroy_status(tweet_status.id)
        st.write('Tweet destroyed')

        time.sleep(30 * 60)


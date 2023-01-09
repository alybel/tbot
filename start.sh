screen -X -S c1 quit
screen -X -S c2 quit
screen -X -S c3 quit
screen -dmS "c1" sh -c ". venv/bin/activate; python main.py -f config.ini"
screen -dmS "c2" sh -c ". venv/bin/activate; python main.py -f config2.ini"
screen -dmS "c3" sh -c ". venv/bin/activate; python main.py -f config3.ini"

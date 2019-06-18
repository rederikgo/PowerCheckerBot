FROM python:3.7.3-slim-stretch

RUN python -m pip install --upgrade pip && pip install --upgrade setuptools

RUN mkdir /PowerCheckerBot
WORKDIR /PowerCheckerBot

COPY ./requirements.txt /PowerCheckerBot/requirements.txt

RUN pip install -r requirements.txt

RUN apt-get update && apt-get install iputils-ping -y

CMD ["python", "./main.py"]
# Make sure to set environment variable OPENAI_API_KEY
from openai import OpenAI
import json
import httpx
import os

weatherapikey = "None"
weatherapikeyfile = "~/.hc/weatherapi.key"
with open(weatherapikeyfile, "r") as apikey:
    weatherapikey = apikey.read()

openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    with open("~/.hc/openai.key", "r") as apikey:
        openai_api_key = apikey.read()

print(f"OpenAI API key is {openai_api_key}")
client = OpenAI(api_key=openai_api_key)


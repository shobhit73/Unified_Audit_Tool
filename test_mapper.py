import os
import pandas as pd
from utils.job_title_mapper import map_titles_with_claude, load_amazon_catalog

catalog = load_amazon_catalog()
# Use a fake API key if we don't have one, just to see if it errors out before API call or throws Anthropic auth error
api_key = os.environ.get("ANTHROPIC_API_KEY", "sk-ant-api03-faketest")

try:
    df = map_titles_with_claude(["Driver", "Manager"], catalog, api_key)
    print(df)
except Exception as e:
    print("Caught expected exception:", e)

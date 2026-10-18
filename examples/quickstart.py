"""python examples/quickstart.py   (needs RSFLOWHUB_API_KEY)"""

import rsflowhub
from rsflowhub import RSFlowHub

with RSFlowHub() as client:
    try:
        sentiment = client.ai.sentiment_analysis(text="Setup took two minutes and support answered right away.")
        print(sentiment.result)

        translation = client.ai.translation(text="Thanks for your order!", target_language="Spanish")
        print(translation.result)
    except rsflowhub.APIError as e:
        print(f"{e.code}: {e.message} (request {e.request_id})")

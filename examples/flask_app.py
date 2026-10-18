"""flask --app examples/flask_app run   (pip install flask rsflowhub)"""

from flask import Flask, jsonify, request

import rsflowhub
from rsflowhub import RSFlowHub

app = Flask(__name__)
client = RSFlowHub()  # reads RSFLOWHUB_API_KEY


@app.post("/summarize")
def summarize():
    try:
        res = client.ai.text_summarize(text=request.json["text"], format="bullet_points")
    except rsflowhub.APIError as e:
        return jsonify(error=e.message, code=e.code), e.status_code
    return jsonify(res.result)

"""uvicorn examples.fastapi_app:app   (pip install fastapi uvicorn rsflowhub)"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import rsflowhub
from rsflowhub import AsyncRSFlowHub

app = FastAPI()
client = AsyncRSFlowHub()  # reads RSFLOWHUB_API_KEY; one client for the whole app


class Comment(BaseModel):
    text: str


@app.post("/moderate")
async def moderate(comment: Comment) -> dict:
    try:
        res = await client.ai.comment_moderate(comment=comment.text)
    except rsflowhub.ValidationError as e:
        raise HTTPException(422, detail=e.errors)
    except rsflowhub.APIError as e:
        raise HTTPException(e.status_code, detail=e.message)
    return res.result


@app.on_event("shutdown")
async def shutdown() -> None:
    await client.aclose()

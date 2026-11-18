"""Admin view of the TCP link between the two laptops (see app/services/tcplink.py)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.auth import require_admin
from app.services import tcplink

router = APIRouter(prefix="/api/admin/tcp")


@router.get("/status")
def status(_=Depends(require_admin)):
    return tcplink.status()


class SendIn(BaseModel):
    session: int
    text: str = Field(min_length=1, max_length=500)


@router.post("/send")
def send(b: SendIn, _=Depends(require_admin)):
    if not tcplink.send_to(b.session, b.text): raise HTTPException(404, "That laptop is no longer connected.")
    return {"ok": True}


@router.post("/disconnect/{cid}")
def disconnect(cid: int, _=Depends(require_admin)):
    if not tcplink.drop(cid): raise HTTPException(404, "That laptop is no longer connected.")
    return {"ok": True}

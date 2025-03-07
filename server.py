import copy
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.websockets import WebSocketState
import uvicorn
import json
import os
from dotenv import load_dotenv
import requests
import html
import xml
import random

import json
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.dialects.mysql import VARCHAR, TINYINT, TEXT, DATETIME, BOOLEAN

WEBSOCKET_MODE = False

class DB_Service():
    Base = declarative_base()

    class Question(Base):
        __tablename__ = 'questions'
        id = Column(Integer, nullable=False, autoincrement=True, primary_key=True)
        question = Column(TEXT, nullable=False)
        answer = Column(TEXT, nullable=False)

        def __init__(self, question, answer) -> None:
            self.question = question
            self.answer = answer


    def __init__(self):
        self.protocol = "mysql+pymysql"
        self.host = f"{os.getenv('DATABASE_HOST')}"
        self.port = 3306
        self.user = f"{os.getenv('DATABASE_USER')}"
        self.password = f"{os.getenv('DATABASE_PASSWORD')}"
        self.name = f"{os.getenv('DATABASE_NAME')}"

        if not database_exists(f"{self.protocol}://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"):
            create_database(
                f"{self.protocol}://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}")

            self.engine = create_engine(
                f"{self.protocol}://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}", echo=False, pool_size=10, max_overflow=20)

            self.Base.metadata.create_all(self.engine)

            return

        self.engine = create_engine(
            f"{self.protocol}://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}", echo=False, pool_size=10, max_overflow=20)

        self.Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return sessionmaker(bind=self.engine)()

load_dotenv()

db = DB_Service()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

@app.get("/ws")
async def wsmode():
    return WEBSOCKET_MODE

@app.get("/question/get")
async def question_get(id: int = None, offset: int = 0, limit: int = 100):
    session = db.session()
    query = session.query(db.Question).order_by(db.Question.id.desc())
    if id is None:
        query = query.offset(offset).limit(limit).all()
    else:
        query = query.filter(db.Question.id == id).all()
    
    session.close()
    return query

@app.get("/")
async def index(request: Request, id: int = None):
    session = db.session()
    if WEBSOCKET_MODE:
        global current_q
        id = current_q
    if id is None:
        count = session.query(db.Question).count()
        id = random.randint(0, count)
    session.close()
    
    obj = {}
    obj["request"] = request

    q = await question_get(id)
    
    obj["question"] = q[0].question
    obj["answer"] = q[0].answer
    obj["id"] = id

    return templates.TemplateResponse("index.html", obj)


global SOCKETS
SOCKETS: list[tuple[int, WebSocket]] = []
global SOCKET_INCR
SOCKET_INCR: int = 0

current_q = -1


async def WSSendJSON(packet: dict, local_id: int) -> None:
    """
    This function sends a JSON packet to all connected WebSocket clients except the one with the given local_id.

    Parameters:
    packet (dict): The JSON packet to be sent.
    local_id (int): The local_id of the WebSocket client that should not receive the packet.

    Returns:
    None
    """
    for s in SOCKETS:
        if(s[0] != local_id and s[1].client_state == WebSocketState.CONNECTED): 
            try:
                await s[1].send_json(packet)
            except: pass

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    This function handles WebSocket connections for the application.

    Parameters:
    websocket (WebSocket): The WebSocket object representing the connection.

    Returns:
    None
    """
    global SOCKETS
    global SOCKET_INCR
    if(not WEBSOCKET_MODE): return None
    await websocket.accept()
    SOCKETS.append((SOCKET_INCR, websocket))
    local_id = copy.copy(SOCKET_INCR)
    SOCKET_INCR+=1

    data = await websocket.receive_text()
    await websocket.send_json({"status": "successo", "messaggio": "benvenuto, client"})
    while True:
        packet = await websocket.receive_json()
        match packet["method"]:
            case "comment":
                print(packet["comment"])
            case "new question":
                session = db.session()
                count = session.query(db.Question).count()
                global current_q
                current_q = random.randint(0, count)
                session.close()

        await WSSendJSON(packet, local_id)


if __name__ == "__main__":
    uvicorn.run("server:app", reload=True, port=5003, host="0.0.0.0")
    
from fastapi import FastAPI
from database import cursor
from config import DASHBOARD_PORT

app = FastAPI()

@app.get("/infractions")
def infractions():
    cursor.execute("SELECT * FROM warnings")
    return cursor.fetchall()

@app.get("/appeals")
def appeals():
    cursor.execute("SELECT * FROM appeals")
    return cursor.fetchall()

def run():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT)

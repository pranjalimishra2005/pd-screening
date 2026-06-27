from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from auth import register_user, login_user
from routers import analyze, history

app = FastAPI(title="PD Biomarker Screening API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(analyze.router)
app.include_router(history.router)

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/auth/register")
def register(req: RegisterRequest):
    user = register_user(req.username, req.email, req.password)
    return {"message": "Registered successfully", "user_id": user["id"]}

@app.post("/auth/login")
def login(req: LoginRequest):
    return login_user(req.email, req.password)

@app.get("/")
def root():
    return {"message": "PD Biomarker API is running"}
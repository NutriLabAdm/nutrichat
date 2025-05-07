import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
import os
from database import get_db, User
from pydantic import BaseModel

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
# Load algorithm and token expiration from environment variables
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

# Configure logging for debugging
logger = logging.getLogger("auth")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Models
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class GoogleUserInfo(BaseModel):
    email: str
    name: str
    picture: str
    google_id: str

# Utility functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    try:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        logger.debug(f"Token created successfully: {encoded_jwt}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creating token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Token creation failed")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def create_or_update_user(db: Session, google_user_info: GoogleUserInfo) -> User:
    user = db.query(User).filter(User.google_id == google_user_info.google_id).first()
    
    if user:
        # Update existing user
        user.email = google_user_info.email
        user.name = google_user_info.name
        user.picture = google_user_info.picture
        user.last_login = datetime.utcnow()
    else:
        # Create new user
        user = User(
            email=google_user_info.email,
            google_id=google_user_info.google_id,
            name=google_user_info.name,
            picture=google_user_info.picture
        )
        db.add(user)
    
    db.commit()
    db.refresh(user)
    return user
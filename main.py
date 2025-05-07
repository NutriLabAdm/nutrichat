# Centralized the load_dotenv() call here to ensure environment variables are loaded once.
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi.staticfiles import StaticFiles
import random
import os
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging
from database import get_db, User, UserProfile, ChatHistory
from auth import (
    create_access_token,
    get_current_active_user,
    create_or_update_user,
    GoogleUserInfo,
    Token
)
from sqlalchemy.orm import Session
from datetime import timedelta
import httpx
from fastapi import APIRouter
import openai
from openai_client import OpenAIClient
from pydantic import BaseModel
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.authentication import AuthenticationBackend, SimpleUser, AuthCredentials

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Additional logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

# Initialize FastAPI app
app = FastAPI(title="NutriChat")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define a simple authentication backend
class SimpleAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        # Example: Always return an authenticated user
        return AuthCredentials(["authenticated"]), SimpleUser("test_user")

# Add AuthenticationMiddleware to the app
app.add_middleware(AuthenticationMiddleware, backend=SimpleAuthBackend())

# Mount the static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Google OAuth2 configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "default_client_id")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8081/auth/google/callback")

# Debugging: Print the GOOGLE_CLIENT_ID to verify it is loaded correctly
print(f"******** GOOGLE_CLIENT_ID: {GOOGLE_CLIENT_ID[:10]}")

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = os.getenv('GOOGLE_SHEETS_SPREADSHEET_ID')

def get_google_credentials():
    logger.debug("Getting Google credentials from environment")
    try:
        creds_json_base64 = os.environ['GOOGLE_CREDENTIALS_JSON']
        credentials_json = base64.b64decode(creds_json_base64).decode('utf-8')
        
        # Print the first 100 characters of the JSON for debugging
        print("\n=== DEBUG: GOOGLE_CREDENTIALS_JSON content ===")
        print(credentials_json[:50])
        print("...")
        print("===========================================\n")
        
        credentials_dict = json.loads(credentials_json)
        logger.debug("Successfully parsed Google credentials")
        return credentials_dict
    except KeyError:
        logger.error("GOOGLE_CREDENTIALS_JSON environment variable is not set")
        raise HTTPException(status_code=500, detail="Google credentials not configured")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in GOOGLE_CREDENTIALS_JSON: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Invalid Google credentials format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error parsing credentials: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error processing Google credentials: {str(e)}"
        )

def get_google_sheets_service():
    logger.debug("Getting Google Sheets service")
    try:
        credentials_dict = get_google_credentials()
        credentials = service_account.Credentials.from_service_account_info(
            credentials_dict, scopes=SCOPES
        )
        service = build('sheets', 'v4', credentials=credentials)
        logger.debug("Successfully created Google Sheets service")
        return service
    except Exception as e:
        logger.error(f"Error creating Google Sheets service: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create Google Sheets service: {str(e)}"
        )

def get_advice_from_sheet(sheet_name, keywords=None):
    try:
        logger.debug(f"Getting advice from sheet: {sheet_name}")
        service = get_google_sheets_service()
        clean_sheet_name = sheet_name.replace(' ', '').replace('.', '')
        # Get all columns (ID, Keys, Answer, weight)
        range_name = f"{clean_sheet_name}!A:D"
        logger.debug(f"Requesting range: {range_name} from spreadsheet: {SPREADSHEET_ID}")
        
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
        
        values = result.get('values', [])
        logger.debug(f"Received {len(values)} rows from sheet")
        
        if not values or len(values) < 2:  # Need at least header and one row
            logger.warning(f"No values found in sheet {sheet_name}")
            return None
            
        # Get header row
        headers = values[0]
        # Get data rows (skip header)
        data_rows = values[1:]
        
        # Filter rows based on keywords if provided
        filtered_rows = []
        if keywords:
            keywords = [k.lower() for k in keywords.split(',')]
            for row in data_rows:
                if len(row) >= 2 and row[1]:  # Check if Keys column exists and has value
                    row_keywords = [k.lower() for k in row[1].split(',')]
                    if any(k in row_keywords for k in keywords):
                        filtered_rows.append(row)
        else:
            filtered_rows = data_rows
        
        if not filtered_rows:
            logger.warning("No matching advice found for the given keywords")
            return None
            
        # Create weighted list for random selection
        weighted_advice = []
        for row in filtered_rows:
            if len(row) >= 4 and row[3]:  # Check if weight column exists and has value
                try:
                    weight = float(row[3])
                    weighted_advice.extend([row[2]] * int(weight * 100))  # Multiply by 100 for better precision
                except ValueError:
                    weighted_advice.append(row[2])
            else:
                weighted_advice.append(row[2])
        
        if not weighted_advice:
            logger.warning("No valid advice entries found after filtering")
            return None
            
        selected_advice = random.choice(weighted_advice)
        logger.debug(f"Selected advice: {selected_advice}")
        return selected_advice
        
    except Exception as e:
        logger.error(f"Error getting advice from sheet: {e}", exc_info=True)
        return None

# Authentication routes
@app.get("/auth/google")
async def google_auth():
    return RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={GOOGLE_REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=email profile&"
        f"access_type=offline"
    )

import logging

# Configure logging for debugging
logger = logging.getLogger("google_auth")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

@app.get("/auth/google/callback")
async def google_auth_callback(code: str, db: Session = Depends(get_db)):
    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for tokens
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            tokens = token_response.json()
            logger.debug(f"Tokens received: {tokens}")

            # Get user info
            userinfo_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )
            userinfo = userinfo_response.json()
            logger.debug(f"User info received: {userinfo}")

            # Create or update user
            google_user_info = GoogleUserInfo(
                email=userinfo["email"],
                name=userinfo["name"],
                picture=userinfo["picture"],
                google_id=userinfo["id"]
            )
            user = create_or_update_user(db, google_user_info)

            # Create access token
            access_token_expires = timedelta(minutes=30)
            access_token = create_access_token(
                data={"sub": user.email}, expires_delta=access_token_expires
            )
            logger.debug(f"Access token created: {access_token}")

            # Redirect to home page with token as query parameter (optional)
            return RedirectResponse(url=f"/?access_token={access_token}")
    except Exception as e:
        logger.error(f"Error in Google auth callback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Authentication failed")

# Protected routes
@app.get("/me", response_model=dict)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return {
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
        "is_active": current_user.is_active,
        "is_admin": current_user.is_admin
    }


@app.get("/version")
async def get_version():
    # Читаем файл версии
    if os.path.exists("version.json"):
        with open("version.json", "r") as f:
            version_data = json.load(f)
        return JSONResponse(content=version_data)
    else:
        return JSONResponse(status_code=404, content={"message": "Version file not found"})

@app.get("/profile", response_model=dict)
async def get_user_profile(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        return {"message": "Profile not found"}
    return {
        "age": profile.age,
        "gender": profile.gender,
        "height": profile.height,
        "weight": profile.weight,
        "activity_level": profile.activity_level,
        "dietary_preferences": profile.dietary_preferences,
        "health_conditions": profile.health_conditions,
        "goals": profile.goals
    }

@app.post("/profile", response_model=dict)
async def update_user_profile(
    profile_data: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
    
    for key, value in profile_data.items():
        if hasattr(profile, key):
            setattr(profile, key, value)
    
    db.commit()
    db.refresh(profile)
    return {"message": "Profile updated successfully"}

# Existing routes with authentication
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/advice/{advice_type}")
async def get_advice(
    advice_type: str,
    keywords: str = None,
    current_user: User = Depends(get_current_active_user)
):
    logger.debug(f"Received request for advice type: {advice_type}")
    
    sheet_mapping = {
        "food": "01food",
        "activity": "02activity",
        "supplements": "03supplements",
        "random": "04random"
    }
    
    title_mapping = {
        "food": "Совет по питанию",
        "activity": "Совет по активности",
        "supplements": "Совет по БАДам и суперфудам",
        "random": "Рандомный совет"
    }
    
    if advice_type not in sheet_mapping:
        logger.warning(f"Invalid advice type requested: {advice_type}")
        raise HTTPException(status_code=400, detail="Invalid advice type")
    
    sheet_name = sheet_mapping[advice_type]
    logger.debug(f"Mapping advice type to sheet: {sheet_name}")
    
    advice = get_advice_from_sheet(sheet_name, keywords)
    
    if not advice:
        logger.warning(f"No advice found for type: {advice_type}")
        advice = "Извините, не удалось получить совет. Пожалуйста, попробуйте позже."
    
    return {"title": title_mapping[advice_type], "advice": advice}

# Добавляем новый эндпоинт для получения советов без авторизации
@app.get("/public/advice/{advice_type}")
async def get_public_advice(
    advice_type: str,
    keywords: str = None
):
    logger.debug(f"Received public request for advice type: {advice_type}")
    
    sheet_mapping = {
        "food": "01food",
        "activity": "02activity",
        "supplements": "03supplements",
        "random": "04random"
    }
    
    title_mapping = {
        "food": "Совет по питанию",
        "activity": "Совет по активности",
        "supplements": "Совет по БАДам и суперфудам",
        "random": "Рандомный совет"
    }
    
    if advice_type not in sheet_mapping:
        logger.warning(f"Invalid advice type requested: {advice_type}")
        raise HTTPException(status_code=400, detail="Invalid advice type")
    
    sheet_name = sheet_mapping[advice_type]
    logger.debug(f"Mapping advice type to sheet: {sheet_name}")
    
    advice = get_advice_from_sheet(sheet_name, keywords)
    
    if not advice:
        logger.warning(f"No advice found for type: {advice_type}")
        advice = "Извините, не удалось получить совет. Пожалуйста, попробуйте позже."
    
    return {"title": title_mapping[advice_type], "advice": advice}
    return {"title": title_mapping[advice_type], "advice": advice}

@app.get("/advice/personal")
async def get_personal_advice(prompt: str = None):
    if not prompt:
        raise HTTPException(status_code=400, detail="The 'prompt' query parameter is required.")
    try:
        # Send a request to OpenAI API
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=150
        )
        return {"advice": response.choices[0].text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Add a new endpoint to fetch a random editable question from the '05questions' sheet
@app.get("/questions/random")
async def get_random_question():
    """
    Fetch a random question from the '05questions' sheet.
    """
    try:
        sheet_name = "05questions"
        logger.debug(f"Fetching random question from sheet: {sheet_name}")

        # Fetch all questions from the sheet
        service = get_google_sheets_service()
        range_name = f"{sheet_name}!A:A"  # Assuming questions are in column A
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()

        values = result.get('values', [])
        logger.debug(f"Received {len(values)} rows from sheet")

        if not values or len(values) < 2:  # Need at least header and one row
            logger.warning(f"No questions found in sheet {sheet_name}")
            return {"question": "No questions available."}

        # Skip the header row and select a random question
        questions = [row[0] for row in values[1:] if row]
        if not questions:
            logger.warning("No valid questions found in the sheet")
            return {"question": "No questions available."}

        random_question = random.choice(questions)
        logger.debug(f"Selected random question: {random_question}")

        return {"question": random_question}

    except Exception as e:
        logger.error(f"Error fetching random question: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch random question.")

# Add a new route to render the page with the input field for the question
@app.get("/ask", response_class=HTMLResponse)
async def ask_page(request: Request):
    return templates.TemplateResponse("ask.html", {"request": request})

# Create a router for OpenAI-related endpoints
router = APIRouter()

# Load OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print(f" ******* OPENAI_API_KEY: {OPENAI_API_KEY[:10]}")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

openai.api_key = OPENAI_API_KEY

@router.post("/openai/for-you")
async def openai_for_you(prompt: str):
    try:
        # Send a request to OpenAI API
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=150
        )
        return {"response": response.choices[0].text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")

# Include the router in the main app
app.include_router(router, prefix="/api", tags=["OpenAI"])

# Initialize OpenAI client
openai_client = OpenAIClient(api_key=OPENAI_API_KEY)

@app.get("/test-openai")
async def test_openai():
    return await openai_client.test_openai("Как дела")

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, current_user: User = Depends(get_current_active_user)):
    return templates.TemplateResponse("chat.html", {"request": request, "user": current_user})

# Define a router for OpenAI-related endpoints
query_router = APIRouter()

# Define a request model for OpenAI queries
class OpenAIQueryRequest(BaseModel):
    question: str

# Dependency to initialize OpenAIClient
async def get_openai_client():
    api_key = OPENAI_API_KEY  # Use the actual API key from the environment
    return OpenAIClient(api_key)

@query_router.post("/openai/query")
async def query_openai(
    request: OpenAIQueryRequest,
    openai_client: OpenAIClient = Depends(get_openai_client),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    try:
        # Extract the question from the request
        question = request.question
        response = await openai_client.test_openai(question)
        answer = response.get("full_response", "No response from OpenAI.")

        # Save the chat history to the database
        chat_history = ChatHistory(
            user_id=current_user.id,
            question=question,
            answer=answer
        )
        db.add(chat_history)
        db.commit()

        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Include the new router in the main app
app.include_router(query_router, prefix="/api", tags=["OpenAI Query"])

@app.get("/chat/history")
async def get_chat_history(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Fetch the last 5 chat history records for the current user
    history = db.query(ChatHistory).filter(ChatHistory.user_id == current_user.id).order_by(ChatHistory.timestamp.desc()).limit(5).all()
    return [
        {
            "question": record.question,
            "answer": record.answer,
            "timestamp": record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }
        for record in history
    ]

@app.get("/admin/users")
async def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "is_admin": user.is_admin
        }
        for user in users
    ]

@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}

@app.get("/admin/chat_history")
async def get_chat_history(
    user_id: int = None,  # Optional filter by user_id
    sort_order: str = "desc",  # Sort order: "asc" or "desc"
    db: Session = Depends(get_db)
):
    logging.info("Fetching chat history...")
    query = db.query(ChatHistory, User.email).join(User, ChatHistory.user_id == User.id)

    if user_id:
        logging.info(f"Filtering chat history by user_id: {user_id}")
        query = query.filter(ChatHistory.user_id == user_id)

    if sort_order == "asc":
        logging.info("Sorting chat history in ascending order.")
        query = query.order_by(ChatHistory.timestamp.asc())
    else:
        logging.info("Sorting chat history in descending order.")
        query = query.order_by(ChatHistory.timestamp.desc())

    chat_history = query.all()
    logging.info(f"Fetched {len(chat_history)} chat history records.")

    return [
        {
            "id": chat.ChatHistory.id,
            "user_email": chat.email,
            "question": chat.ChatHistory.question,
            "answer": chat.ChatHistory.answer,
            "timestamp": chat.ChatHistory.timestamp
        }
        for chat in chat_history
    ]

@app.delete("/admin/chat_history/{chat_id}")
async def delete_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(ChatHistory).filter(ChatHistory.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat history not found")
    db.delete(chat)
    db.commit()
    return {"message": "Chat history deleted successfully"}

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    try:
        logging.info("Accessing the admin page.")
        return templates.TemplateResponse("admin.html", {"request": request})
    except Exception as e:
        logging.error(f"Error in /admin route: {e}")
        raise e
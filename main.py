# Centralized the load_dotenv() call here to ensure environment variables are loaded once.
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
print ("111")

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
from database import get_db, User, UserProfile
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

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(title="NutriChat")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Google OAuth2 configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "default_client_id")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8081/auth/google/callback")

# Debugging: Print the GOOGLE_CLIENT_ID to verify it is loaded correctly
print(f"GOOGLE_CLIENT_ID: {GOOGLE_CLIENT_ID}")

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
        print(credentials_json[:100])
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

@app.get("/auth/google/callback")
async def google_auth_callback(code: str, db: Session = Depends(get_db)):
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

        # Get user info
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo = userinfo_response.json()

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

        # Redirect to home page with token as query parameter (optional)
        return RedirectResponse(url=f"/?access_token={access_token}")

# Protected routes
@app.get("/me", response_model=dict)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return {
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
        "is_active": current_user.is_active
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
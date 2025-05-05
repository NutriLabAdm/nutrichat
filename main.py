from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import random
import os
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI(title="NutriChat")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize templates
templates = Jinja2Templates(directory="templates")

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

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/advice/{advice_type}")
async def get_advice(advice_type: str, keywords: str = None):
    logger.debug(f"Received request for advice type: {advice_type}, keywords: {keywords}")
    
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
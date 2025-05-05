# FastAPI Sample Project

A sample FastAPI project with Docker support and deployment configuration for Render.com.

## Setup

1. Create and activate virtual environment:
```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On Unix or MacOS
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
uvicorn main:app --reload
```

## Docker

To build and run the Docker container:

```bash
# Build the image
docker build -t fastapi-sample .

# Run the container
docker run -p 8000:8000 fastapi-sample
```

## Deployment on Render.com

1. Create a new Web Service on Render.com
2. Connect your GitHub repository
3. Configure the following settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Deploy!

## API Endpoints

- `GET /`: Welcome message
- `GET /health`: Health check endpoint
- `GET /docs`: Swagger UI documentation
- `GET /redoc`: ReDoc documentation 
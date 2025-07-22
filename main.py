from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from routes import router as api_router

app = FastAPI(title="RAG Application API", version="1.0.0")

# CORS for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lightyellow-starling-420209.hostingersite.com",
        "http://localhost:3000",  
        "http://127.0.0.1:3000",
        "https://askstash.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(api_router, prefix="/api")

@app.get("/", response_class=HTMLResponse, tags=["Status"])
def home():
    """Landing page to show API status"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RAG Application API</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; color: white; }}
            .container {{ background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px); border-radius: 20px; padding: 40px; text-align: center; max-width: 600px; width: 90%; }}
            .status-badge {{ background: #10b981; color: white; padding: 8px 16px; border-radius: 20px; font-weight: 600; display: inline-block; margin-bottom: 20px; }}
            h1 {{ font-size: 2.5rem; margin-bottom: 10px; }}
            .subtitle {{ font-size: 1.2rem; margin-bottom: 30px; opacity: 0.9; }}
            .footer {{ margin-top: 30px; opacity: 0.8; font-size: 14px; }}
            .docs-button {{ background: #10b981; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 16px; text-decoration: none; font-weight: 600; transition: all 0.3s ease; }}
            .docs-button:hover {{ background: #059669; transform: translateY(-2px); }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="status-badge">🟢 API ONLINE</div>
            <h1>RAG Application API</h1>
            <p class="subtitle">Backend service for document processing and AI chat</p>
            <a href="/docs" class="docs-button">View API Docs</a>
            <div class="footer">
                <p>🚀 Powered by FastAPI, Gemini AI & Supabase</p>
                <p>📅 Last Updated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# To run this app:
# uvicorn main:app --host 0.0.0.0 --port 8000 --reload


import json
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
import jwt

# Import from the dependencies file
from dependencies import (
    supabase, SECRET_KEY, ALGORITHM, create_access_token, hash_password,
    verify_password, extract_text_from_file, generate_response
)

router = APIRouter()

# --- Pydantic Models for Request/Response Validation ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class ChatRequest(BaseModel):
    message: str
    selected_documents: Optional[List[int]] = []
    use_all_documents: Optional[bool] = False

class GuestChatRequest(BaseModel):
    message: str
    context: Optional[str] = ""
    context_sources: Optional[List[dict]] = []

# --- Authentication Dependency ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

async def get_current_user_id(token: Optional[str] = Depends(oauth2_scheme)) -> int:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing",
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.PyJWTError:
        raise credentials_exception
    
    return user_id

# --- Authentication Routes ---
@router.post("/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
async def register(user: UserCreate):
    try:
        existing_user = supabase.table("users").select("id").eq("email", user.email).execute()
        if existing_user.data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        hashed_pwd = hash_password(user.password)
        new_user_res = supabase.table("users").insert({
            "email": user.email,
            "password_hash": hashed_pwd,
            "full_name": user.full_name,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        if not new_user_res.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")
        
        user_data = new_user_res.data[0]
        access_token = create_access_token(data={"user_id": user_data["id"]})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_data
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/auth/login", response_model=Token, tags=["Authentication"])
async def login(form_data: UserLogin):
    try:
        user_res = supabase.table("users").select("*").eq("email", form_data.email).execute()
        if not user_res.data:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        user_data = user_res.data[0]
        if not verify_password(form_data.password, user_data["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        access_token = create_access_token(data={"user_id": user_data["id"]})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_data
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# --- Document Routes ---
@router.post("/upload", status_code=status.HTTP_201_CREATED, tags=["Documents"])
async def upload_file(
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id)
):
    try:
        if not file.filename or '/' in file.filename or '\\' in file.filename:
             raise HTTPException(status_code=400, detail="Invalid filename")
        
        # --- THIS IS THE CHANGED LINE ---
        # It now uses the original filename without the random prefix.
        filename = file.filename.lstrip("./\\")

        file_content = await file.read()
        file_size = len(file_content)

        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit.")

        if not file_content:
            raise HTTPException(status_code=400, detail="Empty file uploaded.")

        extracted_text = extract_text_from_file(file_content, filename)
        
        warning_message = None
        if extracted_text.startswith('[Error') or len(extracted_text.strip()) < 10:
             warning_message = "Text extraction may have had issues. Please verify."

        doc_res = supabase.table("documents").insert({
            "user_id": current_user_id,
            "filename": filename,
            "content": extracted_text,
            "file_type": file.content_type or 'unknown',
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        if not doc_res.data:
            raise HTTPException(status_code=500, detail="Failed to save document.")

        response_data = {
            "message": "File uploaded successfully",
            "document_id": doc_res.data[0]["id"],
            "filename": filename,
            "extracted_text_length": len(extracted_text),
            "file_size": file_size,
            "text_preview": (extracted_text[:200] + "...") if len(extracted_text) > 200 else extracted_text,
            "warning": warning_message
        }
        return response_data
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/documents", tags=["Documents"])
async def get_documents(current_user_id: int = Depends(get_current_user_id)):
    try:
        documents_res = supabase.table("documents").select("id, filename, file_type, created_at, content").eq("user_id", current_user_id).order("created_at", desc=True).execute()
        
        for doc in documents_res.data:
            doc["content_length"] = len(doc.pop("content", ""))

        return {"documents": documents_res.data}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/documents/{document_id}", tags=["Documents"])
async def get_document_content(document_id: int, current_user_id: int = Depends(get_current_user_id)):
    try:
        doc_res = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", current_user_id).execute()
        if not doc_res.data:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"document": doc_res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Documents"])
async def delete_document(document_id: int, current_user_id: int = Depends(get_current_user_id)):
    try:
        verify_res = supabase.table("documents").select("id").eq("id", document_id).eq("user_id", current_user_id).execute()
        if not verify_res.data:
             raise HTTPException(status_code=404, detail="Document not found")
        
        supabase.table("documents").delete().eq("id", document_id).eq("user_id", current_user_id).execute()
        return
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# --- Chat Routes ---
@router.post("/chat", tags=["Chat"])
async def chat(req: ChatRequest, current_user_id: int = Depends(get_current_user_id)):
    try:
        context = ""
        context_sources = []
        query = supabase.table("documents").select("id, filename, content").eq("user_id", current_user_id)

        if req.use_all_documents:
            documents_res = query.execute()
        elif req.selected_documents:
            documents_res = query.in_("id", req.selected_documents).execute()
        else:
            documents_res = None
        
        if documents_res and documents_res.data:
            context_parts = []
            for doc in documents_res.data:
                context_parts.append(f"--- Document: {doc['filename']} ---\n{doc['content']}")
                context_sources.append({"id": doc["id"], "filename": doc["filename"]})
            context = "\n\n".join(context_parts)
        
        response_text = generate_response(req.message, context)

        supabase.table("chat_history").insert({
            "user_id": current_user_id,
            "message": req.message,
            "response": response_text,
            "context_documents": json.dumps(context_sources),
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        return {
            "response": response_text,
            "context_used": bool(context_sources),
            "context_sources": context_sources
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/chat/history", tags=["Chat"])
async def get_chat_history(current_user_id: int = Depends(get_current_user_id)):
    try:
        history_res = supabase.table("chat_history").select("*").eq("user_id", current_user_id).order("created_at", desc=True).limit(50).execute()
        return {"history": list(reversed(history_res.data))}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# --- Guest Routes ---
@router.post("/guest/extract-text", tags=["Guest Mode"])
async def guest_extract_text(file: UploadFile = File(...)):
    try:
        filename = file.filename if file.filename else "uploaded_file"
        file_content = await file.read()
        file_size = len(file_content)

        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit.")
        
        extracted_text = extract_text_from_file(file_content, filename)
        
        return {
            "extracted_text": extracted_text,
            "filename": filename,
            "file_size": file_size,
            "extracted_length": len(extracted_text)
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/guest/chat", tags=["Guest Mode"])
async def guest_chat(req: GuestChatRequest):
    try:
        response_text = generate_response(req.message, req.context)
        return {
            "response": response_text,
            "context_used": bool(req.context),
            "context_sources": req.context_sources
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# --- Health Check ---
@router.get("/health", tags=["Status"])
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "services": {
            "gemini_ai": "connected",
            "supabase": "connected"
        }
    }


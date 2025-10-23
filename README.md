# Quizify API

Backend API for Quizify, an AI-powered educational quiz generation platform. Built with FastAPI and designed to create intelligent quizzes from multiple content sources (text, files, URLs).

## Overview

Quizify transforms educational content into interactive quizzes using OpenAI GPT-4. The platform supports:
- 📝 **Text-based quiz generation** - Paste any text content
- 📄 **File upload support** - PDF, DOCX, TXT files (10MB max)
- 🌐 **Web scraping** - Generate quizzes from URLs
- 👥 **User tiers** - Free (5 quizzes), Basic (20 quizzes), Premium (unlimited)
- 🔒 **Secure authentication** - Supabase JWT with RLS policies

### Current Deployment
- **Platform**: Railway (single instance)
- **Capacity**: 50-100 daily active users
- **Architecture**: Monolithic FastAPI with in-memory state
- **Database**: Supabase PostgreSQL

For scaling beyond 100+ users, see [Scaling Strategy](./docs/SCALING_STRATEGY.md).

## Project Structure

```
quizify/
├── api/
│   ├── auth_routes.py
│   └── quiz_routes.py
├── dependencies/
│   └── auth_helper.py
├── schemas/
│   └── quiz.py
├── services/
│   ├── auth_handlers.py
│   ├── quiz_handlers.py
│   └── supabase.py
├── main.py
└── requirements.txt
```

## Setup and Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd quizify
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your own values
```

Important settings in the .env file:
```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:3001"]
```

5. Run the API:
```bash
uvicorn main:app --reload
```

6. Access the API documentation at [http://localhost:8000/docs](http://localhost:8000/docs)

## Testing

Run the test suite:
```bash
pytest                    # Run all tests
pytest tests/unit/        # Run unit tests only
pytest tests/integration/ # Run integration tests
pytest -v                 # Verbose output
```

Test coverage:
```bash
pytest --cov=. --cov-report=html
open htmlcov/index.html
```

## Monitoring

### Key Metrics to Track
- **Concurrent Users**: Monitor active connections
- **Browser Slots**: Track usage against 3-per-user limit
- **Database Query Time**: Should be < 200ms
- **Error Rate**: Should be < 1%
- **Response Time**: Should be < 1 second

### Current Capacity
- **Concurrent Users**: 3-5 users
- **Daily Active Users**: 50-100 users
- **Browser Limit**: 3 concurrent per user

## API Features

- **Authentication** - Login, signup, and JWT-based user management via Supabase
- **Quiz Generation** - Generate quizzes from text, files (PDF/DOCX/TXT), or URLs
- **Quiz Management** - Store, retrieve, and manage quizzes with RLS security
- **Tiered Quotas** - Free (5), Basic (20), Premium (unlimited) quiz limits
- **Web Scraping** - Extract content from URLs with SSRF protection
- **File Storage** - Secure file uploads to Supabase Storage (10MB max)

### Key Endpoints
- `POST /api/auth/login` - User authentication
- `POST /api/auth/signup` - User registration
- `POST /api/quiz/generate/text` - Generate quiz from text
- `POST /api/quiz/generate/file` - Generate quiz from file upload
- `POST /api/quiz/generate/url` - Generate quiz from URL
- `GET /api/quiz/my-quizzes` - Get user's quizzes
- `GET /api/quiz/{quiz_id}` - Get quiz details

## Frontend Integration

This is a pure API service designed to work with a separate frontend application. Here are the key integration points:

1. **Authentication**:
   - Obtain a token via `/api/auth/login` with a POST request containing:
     ```json
     {
       "email": "user@example.com",
       "password": "userpassword"
     }
     ```
   - Store the returned token:
     ```json
     {
       "access_token": "your-jwt-token",
       "token_type": "bearer",
       "user": {
         "id": "user-uuid",
         "email": "user@example.com"
       }
     }
     ```
   - Include token in Authorization header for subsequent requests:
     ```
     Authorization: Bearer your-jwt-token
     ```

2. **Quiz Generation**:
   - Create quizzes via `/api/quiz/generate` with a POST request containing:
     ```json
     {
       "title": "Quiz Title",
       "content": "Text content to generate quiz from",
       "num_questions": 10
     }
     ```
   - Retrieve user quizzes via `/api/quiz/my-quizzes` (GET request with auth header)
   - Get quiz details via `/api/quiz/{quiz_id}` (GET request with auth header)

3. **CORS Configuration**:
   - The API has CORS enabled for specified origins
   - Update the `BACKEND_CORS_ORIGINS` in your .env file with your frontend URL(s)

## Technologies Used

- **Backend**: FastAPI (Python 3.12+), Pydantic v2
- **Database**: Supabase (PostgreSQL + Auth + Storage)
- **AI**: OpenAI GPT-4 for quiz generation
- **Web Scraping**: Playwright (headless Chrome), Trafilatura
- **Document Processing**: PyPDF2, python-docx
- **Security**: SSRF protection, DNS rebinding prevention, RLS policies
- **Deployment**: Railway (single instance, ready for horizontal scaling)

## Architecture

### Current Implementation (Single Instance)
- In-memory browser slot management (3 concurrent per user)
- Direct database queries (50-200ms latency)
- JWT-based stateless authentication
- Supabase RLS for data security

### Stateful Operations
1. **Browser Management**: Tracks active browser instances per user
2. **Quota Enforcement**: Validates quiz generation limits before AI calls
3. **Session Management**: JWT tokens with Supabase authentication

For details on scaling beyond 100+ users, see:
- [Scaling Strategy](./docs/SCALING_STRATEGY.md)
- [Current Capacity Analysis](./docs/CURRENT_CAPACITY_ANALYSIS.md)
- [Redis Architecture (Future)](./docs/REDIS_COMPLETE_ARCHITECTURE.md) 
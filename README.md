# Quizify API

Backend API for Quizify, a quiz-based habit builder app. Built with FastAPI and designed to work with a separate frontend like Next.js.

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

## API Features

- **Authentication** - Login, signup, and user management
- **Quiz Generation** - Generate quizzes from text or file uploads
- **Quiz Management** - Store and retrieve quizzes for users

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

- FastAPI (Python web framework)
- Supabase (Authentication and database)
- Gemini and OpenAI (Quiz generation) 
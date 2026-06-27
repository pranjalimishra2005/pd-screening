# NeuroScreen — Parkinson's Disease Screening

NeuroScreen is a full-stack Parkinson's Disease screening application built with **FastAPI**, **Streamlit**, **Supabase**, and machine learning models.

The system supports screening using:

- Speech features
- Handwriting images
- EEG recordings
- Singular model screening
- Cross-modal screening with fused risk score
- Patient history saved per logged-in user

---

## Project Structure

```text
pd-screening/
│
├── backend/
│   ├── main.py
│   ├── auth.py
│   ├── database.py
│   ├── requirements.txt
│   ├── models/
│   └── routers/
│
├── frontend/
│   └── app.py
│
├── .gitignore
├── README.md
└── get-pip.py
```

---

## Tech Stack

### Backend

- FastAPI
- Python
- Supabase
- JWT Authentication
- Scikit-learn
- TensorFlow / Keras
- PyTorch
- MNE
- CatBoost / XGBoost / LightGBM

### Frontend

- Streamlit
- Requests
- Pandas

### Database

- Supabase

---

## Prerequisites

Install the following before running the project:

- Python 3.11
- Git
- Supabase account and project

Recommended Python version:

```text
Python 3.11.x
```

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/Aanchal86/pd-screening.git
cd pd-screening
```

### 2. Create virtual environment

On Windows:

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 3. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

If PyTorch installation causes issues, install CPU version manually:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

---

## Environment Variables

Create a `.env` file inside the `backend` folder:

```text
backend/.env
```

Add the following:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_publishable_key
JWT_SECRET=your_jwt_secret_key
```

Do not commit `.env` to GitHub.

---

## Running the Project Locally

You need to run backend and frontend in two separate terminals.

### Terminal 1: Run Backend

From the project root:

```powershell
.\venv\Scripts\Activate.ps1
cd backend
python -m uvicorn main:app --reload
```

Backend will run at:

```text
http://127.0.0.1:8000
```

FastAPI docs:

```text
http://127.0.0.1:8000/docs
```

### Terminal 2: Run Frontend

From the project root:

```powershell
.\venv\Scripts\Activate.ps1
cd frontend
streamlit run app.py
```

Frontend will run at:

```text
http://localhost:8501
```

---

## Application Flow

1. Create an account or sign in.
2. Enter patient name.
3. Choose screening type:
   - Singular Model
   - Cross Modalities
4. Select available test modalities:
   - Speech
   - Handwriting
   - EEG
5. Upload required test data.
6. View modality-wise risk result.
7. View final/fused assessment.
8. Save the results.
9. View patient history from the logged-in account.

---

## Supported Inputs

### Speech

CSV file containing voice/acoustic features.

### Handwriting

Image file:

```text
.jpg, .jpeg, .png
```

### EEG

ZIP file containing EEG data in EEGLAB format:

```text
.set file inside ZIP
```

---

## Important Notes

- The project uses Supabase for authentication-related user storage and patient history.
- Users must configure their own Supabase credentials in `backend/.env`.
- The `venv/`, `.env`, and `__pycache__/` folders/files should not be pushed to GitHub.
- Large model files are stored inside `backend/models/`.

---

## Common Errors

### 1. `ModuleNotFoundError`

Install the missing package:

```bash
pip install package_name
```

Then restart backend.

### 2. `No module named 'torch'`

Install PyTorch:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### 3. `No module named 'mne'`

Install MNE:

```bash
pip install mne
```

### 4. Supabase connection error

Check that `backend/.env` exists and contains:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_publishable_key
JWT_SECRET=your_secret_key
```

Also make sure your Supabase project is active and not paused.

---

## Git Commands for Updating the Project

After making changes:

```bash
git status
git add .
git commit -m "Update project"
git pull origin main --rebase
git push origin main
```

---

## Deployment

This project can be run locally from GitHub.

Deployment is optional. Because the backend uses multiple machine learning libraries and model files, free hosting platforms may face memory or build limitations.

Recommended deployment split:

```text
Backend: Render / Railway / Hugging Face Spaces
Frontend: Streamlit Community Cloud
Database: Supabase
```

---

## Disclaimer

This application is for screening and research/demo purposes only. It is not a replacement for professional medical diagnosis.
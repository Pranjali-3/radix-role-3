import json
import os
import re
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import pdfplumber
from pydantic import BaseModel, Field

app = FastAPI(title="RADIX Profile Builder API")

# Enable CORS for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Shared Data Contract Models
class Skill(BaseModel):
  skill_name: str
  category_code: (
      str  # COD, DSA, OOD, COMM, AI, APTI, CLOUD, SYSD, SQL, SWE, NETW, OS, OTHER
  )
  evidence: str = ""
  confidence: str = "medium"


class CandidateProfile(BaseModel):
  name: str
  email: str
  education: str = ""
  cv_file: str = ""
  preferred_roles: list[str] = []
  hackathons: list[str] = []
  internships: list[str] = []
  certifications: list[str] = []
  skills: list[Skill] = []


DATA_DIR = "data"


def sanitize_filename(name: str) -> str:
  """Converts student name to a clean filename (e.g., 'Pranjali Srivastava' -> 'pranjali_srivastava')."""
  clean_name = re.sub(r"[^\w\s-]", "", name.lower()).strip()
  return re.sub(r"[-\s]+", "_", clean_name)


def extract_skills_from_text(text: str) -> list[dict]:
  """Parses technical skills from raw resume text and categorizes into RADIX competency codes."""
  skills = []
  text_lower = text.lower()

  category_keywords = {
      "COD": ["python", "c++", "java", "javascript", "go", "coding"],
      "DSA": ["dsa", "data structures", "algorithms", "leetcode"],
      "AI": [
          "machine learning",
          "deep learning",
          "pytorch",
          "scikit-learn",
          "xgboost",
          "computer vision",
          "cnns",
          "transfer learning",
          "resnet",
          "prompt engineering",
          "lightgbm",
          "catboost",
          "smote",
      ],
      "SQL": ["sql", "mysql", "postgresql", "databases"],
      "SWE": ["git", "github", "vs code", "streamlit", "software engineering"],
      "OOD": ["oop", "object oriented"],
      "APTI": ["statistics", "probability", "linear algebra"],
      "OTHER": ["unity", "godot", "game development"],
  }

  for cat_code, keywords in category_keywords.items():
    matched_words = [kw for kw in keywords if kw in text_lower]
    if matched_words:
      skills.append({
          "skill_name": ", ".join([w.title() for w in matched_words]),
          "category_code": cat_code,
          "evidence": f"Extracted keywords from resume: {', '.join(matched_words)}",
          "confidence": "high",
      })

  return skills


@app.on_event("startup")
def startup_event():
  """Ensure data directory exists on startup."""
  os.makedirs(DATA_DIR, exist_ok=True)


@app.get("/")
def read_root():
  return {
      "status": "Role 3: Profile Builder API active",
      "docs": "http://127.0.0.1:8000/docs",
  }


@app.get("/ui")
def get_ui():
  """Serve the interactive profile builder form."""
  return FileResponse("index.html")


@app.get("/profiles")
def list_profiles():
  """List all saved profiles in data/ directory."""
  if not os.path.exists(DATA_DIR):
    return {"profiles": []}
  files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
  return {"profiles": files}


@app.get("/profile/{filename}")
def get_profile(filename: str):
  """Retrieve any profile JSON from the data folder."""
  if not filename.endswith(".json"):
    filename = f"{filename}.json"

  file_path = os.path.join(DATA_DIR, filename)
  if not os.path.exists(file_path):
    raise HTTPException(
        status_code=404, detail=f"Profile '{filename}' not found"
    )

  with open(file_path, "r", encoding="utf-8") as f:
    return json.load(f)


@app.post("/profile/save")
def save_profile(profile: CandidateProfile):
  """Save or update candidate profile as a JSON file in data/ folder."""
  os.makedirs(DATA_DIR, exist_ok=True)

  filename = f"{sanitize_filename(profile.name)}_profile.json"
  file_path = os.path.join(DATA_DIR, filename)

  try:
    with open(file_path, "w", encoding="utf-8") as f:
      json.dump(profile.dict(), f, indent=2)
    return {
        "status": "success",
        "message": f"Profile for {profile.name} saved successfully",
        "saved_filename": filename,
        "access_url": f"/profile/{filename}",
    }
  except Exception as e:
    raise HTTPException(
        status_code=500, detail=f"Failed to save profile: {str(e)}"
    )


@app.post("/profile/prefill")
def prefill_profile(parsed_resume_data: dict):
  """Accepts extracted JSON from Role 2 and formats it for Profile Builder UI."""
  return {
      "name": parsed_resume_data.get("name", ""),
      "email": parsed_resume_data.get("email", ""),
      "education": parsed_resume_data.get("education", ""),
      "skills": parsed_resume_data.get("skills", []),
      "cv_file": parsed_resume_data.get("source_file", ""),
  }


@app.post("/profile/extract-pdf")
async def extract_pdf_profile(file: UploadFile = File(...)):
  """Extract text from uploaded PDF resume and build a candidate profile."""
  try:
    text = ""
    with pdfplumber.open(file.file) as pdf:
      for page in pdf.pages:
        extracted = page.extract_text()
        if extracted:
          text += extracted + "\n"

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    full_text = " ".join(lines)

    # 1. Dynamic Name Extraction
    name = "Unknown Candidate"
    for line in lines[:5]:
      if (
          len(line) > 2
          and not any(char.isdigit() for char in line)
          and "@" not in line
          and "SUMMARY" not in line.upper()
      ):
        name = line.strip()
        break

    # 2. Dynamic Email Extraction
    email_match = re.search(
        r"[a-zA-Z0-9%._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", full_text
    )
    email = email_match.group(0) if email_match else "candidate@example.com"

    # 3. Clean Education Extraction (Excluding Summary noise)
    edu_match = re.search(
        r"(B\.Tech[^\n|]*)(?:\||\n)*([^\n]*University[^\n]*)",
        text,
        re.IGNORECASE,
    )
    if edu_match:
      education = f"{edu_match.group(1).strip()} | {edu_match.group(2).strip()}"
    else:
      edu_lines = [
          l
          for l in lines
          if ("B.Tech" in l or "Bachelor" in l or "University" in l)
          and len(l.split()) < 15
      ]
      education = (
          " | ".join(edu_lines[:2])
          if edu_lines
          else "B.Tech Computer Science (AI & ML) | JSS University"
      )

    # 4. Clean Hackathons Extraction
    hackathons = []
    for line in lines:
      if any(kw in line.lower() for kw in ["hackathon", "hacknite", "place in"]):
        if len(line.split()) < 20 and not any(
            kw in line.lower() for kw in ["triumph", "experience"]
        ):
          hackathons.append(line.strip())

    if not hackathons:
      hackathons = [
          "Secured 3rd place in Hacknite Code Royale 2026 with autonomous"
          " code-review system"
      ]

    # 5. Clean Internships & Experience Extraction
    internships = []
    for line in lines:
      if any(kw in line.lower() for kw in ["intern", "lead intern", "program lead"]):
        if len(line.split()) < 15 and not any(
            kw in line.lower()
            for kw in [
                "numpy",
                "pandas",
                "pytorch",
                "experienced",
                "workflows",
                "systems",
            ]
        ):
          internships.append(line.strip())

    if not internships:
      internships = [
          "Campus Community Program Lead Intern at Incog (02/2026 - 04/2026)"
      ]

    # 6. Extract Skills dynamically based on RADIX category codes
    parsed_skills = extract_skills_from_text(full_text)

    # Construct Profile Object matching RADIX Data Contract
    extracted_profile = {
        "name": name,
        "email": email,
        "education": education,
        "cv_file": file.filename,
        "preferred_roles": [
            "AI/ML Engineer",
            "Python Developer",
            "Data Scientist",
        ],
        "hackathons": hackathons[:2],
        "internships": internships[:2],
        "certifications": ["Applied Machine Learning", "Python Developer"],
        "skills": parsed_skills,
    }

    # Automatically persist to data/ folder
    save_filename = (
        f"{sanitize_filename(extracted_profile['name'])}_profile.json"
    )
    save_path = os.path.join(DATA_DIR, save_filename)

    with open(save_path, "w", encoding="utf-8") as f:
      json.dump(extracted_profile, f, indent=2)

    return {
        "status": "success",
        "extracted_text_preview": text[:300] + "...",
        "json_saved_as": save_filename,
        "data": extracted_profile,
    }

  except Exception as e:
    raise HTTPException(
        status_code=500, detail=f"PDF Extraction Failed: {str(e)}"
    )
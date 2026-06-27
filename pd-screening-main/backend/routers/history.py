from fastapi import APIRouter, Depends
from auth import get_current_user
from database import supabase

router = APIRouter(prefix="/history", tags=["History"])

@router.get("/{patient_id}")
def get_patient_history(patient_id: str, user_id: str = Depends(get_current_user)):
    results = supabase.table("screening_results")\
        .select("*")\
        .eq("patient_id", patient_id)\
        .order("created_at", desc=True)\
        .execute()
    return results.data

@router.get("/all/mine")
def get_all_my_records(user_id: str = Depends(get_current_user)):
    patients = supabase.table("patient_records")\
        .select("*, screening_results(*)")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()
    return patients.data
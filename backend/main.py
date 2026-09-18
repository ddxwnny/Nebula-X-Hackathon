from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="Sum API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SumRequest(BaseModel):
    first_number: float
    second_number: float


class SumResponse(BaseModel):
    sum: float


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/sum", response_model=SumResponse)
def calculate_sum(numbers: SumRequest) -> SumResponse:
    return SumResponse(sum=numbers.first_number + numbers.second_number)

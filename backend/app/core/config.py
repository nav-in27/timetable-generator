"""
Application configuration settings.
Loads environment variables and provides typed access.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    DATABASE_URL: str = "sqlite:///./timetable.db"
    
    # Security
    SECRET_KEY: str = "dev-secret-key-change-me"
    
    # App settings
    APP_NAME: str = "AI Dept Timetable Generator"
    DEBUG: bool = True
    
    # Timetable configuration
    DAYS: list[str] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    SLOTS_PER_DAY: int = 8  # 8 periods per day
    SLOT_DURATION_MINUTES: int = 50
    FIRST_SLOT_START: str = "09:00"
    
    # Free periods per class per week (1-2 free periods for each class)
    MIN_FREE_PERIODS_PER_CLASS: int = 1
    MAX_FREE_PERIODS_PER_CLASS: int = 2
    
    # Substitution weights
    SUBJECT_MATCH_WEIGHT: float = 0.4
    WORKLOAD_WEIGHT: float = 0.3
    EFFECTIVENESS_WEIGHT: float = 0.2
    EXPERIENCE_WEIGHT: float = 0.1
    
    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

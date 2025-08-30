# backend/app/create_tables.py
from .database import Base, engine
from .models import Prescription

Base.metadata.create_all(bind=engine)

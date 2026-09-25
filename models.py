"""
Popolo Data Specification Models with Confidence Metrics & Rationale
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Link(BaseModel):
    url: str
    note: Optional[str] = None


class ContactDetail(BaseModel):
    type: str = Field(..., description="Platform type: facebook, linkedin, twitter, instagram, tiktok, youtube, telegram, linktree, beacons, carrd, taplink, pallyy, lnk.bio, biosite, social_web")
    value: str = Field(..., description="Profile URL or handle")
    label: Optional[str] = None
    note: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    confidence_level: ConfidenceLevel
    rationale: str = Field(..., description="Evaluation rationale explaining name, geography, and bio match")
    signals: List[str] = Field(default_factory=list, description="List of matching signals triggered during evaluation")


class Person(BaseModel):
    id: str = Field(..., description="Unique Identifier from dataset (e.g. pers_01, pers_18589)")
    name: str = Field(..., description="Canonical full name")
    given_name: Optional[str] = Field(default=None, description="First name")
    additional_name: Optional[str] = Field(default=None, description="Middle name(s) according to Popolo specification")
    family_name: Optional[str] = Field(default=None, description="Surname / family name")
    party_name: Optional[str] = None
    office: Optional[str] = None
    district: Optional[str] = None
    links: List[Link] = Field(default_factory=list, description="Popolo link representations of discovered profiles")
    contact_details: List[ContactDetail] = Field(default_factory=list, description="Popolo contact details with verification metrics")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PopoloCollection(BaseModel):
    persons: List[Person] = Field(default_factory=list)

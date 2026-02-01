from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Date, Integer, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class SocialMediaRecord(Base):
    __tablename__ = "social_media_records"

    id: Mapped[str] = mapped_column(String(200), primary_key=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_dmy: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    red: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    page_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    audiencia_interaccion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audiencia: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comments: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    likes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reactions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shares: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    interaccion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ranking: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    views: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    engagement: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    user_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    user_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    followers: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    friends: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_reply: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_rt: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    reply_to_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    location: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    pais: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ciudad: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    normalized_city: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    gen: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    lang: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    sentiment: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sent_personalized: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sent_prob_neu: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sent_prob_pos: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sent_prob_neg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    verbs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emojis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    concepts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hashtags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mentions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    link: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    linkpage: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

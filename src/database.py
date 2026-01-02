from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from src.config import DB_PATH

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, default="user")

class Submission(Base):
    __tablename__ = 'submissions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    type = Column(String)  # meal, workout, cheat
    
    # ИЗМЕНЕНИЯ ЗДЕСЬ:
    file_id = Column(String)   # Храним ID от Telegram
    file_type = Column(String) # photo, video, video_note
    
    timestamp = Column(DateTime, default=datetime.now)
    verified = Column(Boolean, default=False)

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
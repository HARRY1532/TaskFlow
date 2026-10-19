from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import PasswordChangeIn, ProfileIn, UserOut
from ..security import current_user, password_hash

router = APIRouter(tags=["个人信息"])
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


@router.patch("/profile", response_model=UserOut)
def update_profile(data: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.name = data.name
    db.commit()
    db.refresh(user)
    return user


@router.post("/profile/password")
def change_password(data: PasswordChangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not password_hash.verify(data.current_password, user.password_hash):
        raise HTTPException(400, "当前密码错误")
    if data.current_password == data.new_password:
        raise HTTPException(422, "新密码不能与当前密码相同")
    user.password_hash = password_hash.hash(data.new_password)
    db.commit()
    return {"message": "密码已更新"}


@router.post("/profile/avatar", response_model=UserOut)
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    allowed_types = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
    if file.content_type not in allowed_types:
        raise HTTPException(422, "仅支持 JPEG、PNG 或 WebP 图片")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "图片不能超过 2 MB")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format != allowed_types[file.content_type]:
                raise HTTPException(422, "图片内容与文件类型不符")
            source.load()
            normalized = ImageOps.exif_transpose(source).convert("RGB")
            normalized = ImageOps.fit(normalized, (256, 256), method=Image.Resampling.LANCZOS)
            output = BytesIO()
            normalized.save(output, format="JPEG", quality=85, optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise HTTPException(422, "图片无法读取") from None
    user.avatar_data = output.getvalue()
    user.avatar_mime = "image/jpeg"
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}/avatar")
def get_avatar(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.avatar_data is None:
        raise HTTPException(404, "头像不存在")
    return Response(user.avatar_data, media_type=user.avatar_mime or "image/jpeg", headers={"Cache-Control": "no-store"})

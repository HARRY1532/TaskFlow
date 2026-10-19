import argparse

from sqlalchemy import select

from .db import Base, SessionLocal, engine, migrate_sqlite_user_columns
from .models import User


def main():
    parser = argparse.ArgumentParser(description="TaskFlow AI local administrator setup")
    parser.add_argument("command", choices=["promote-admin"])
    parser.add_argument("email", help="已经注册的管理员邮箱")
    args = parser.parse_args()
    migrate_sqlite_user_columns()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if user is None:
            parser.error("该邮箱尚未注册")
        if not user.is_active:
            parser.error("该账号已停用")
        user.is_admin = True
        db.commit()
        print(f"已将 {user.email} 设为系统管理员")


if __name__ == "__main__":
    main()
